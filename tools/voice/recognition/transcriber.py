"""Coordinates transcription providers with fallback chain.

Selects the best available provider, falls back on failure.
Logs accuracy for comparison when multiple providers are available.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import yaml

from tools.voice import CONFIG_PATH, get_connection
from tools.voice.models import TranscriptionResult

logger = logging.getLogger(__name__)


def _load_voice_config() -> dict[str, Any]:
    """Load voice configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class TranscriptionCoordinator:
    """Manages transcription provider selection, fallback, and accuracy tracking.

    Priority: user_preference → whisper_api → web_speech (browser-side)
    """

    def __init__(self):
        self._config = _load_voice_config()
        self._providers: dict[str, Any] = {}
        self._register_providers()

    def _register_providers(self) -> None:
        """Register available transcription providers."""
        from tools.voice.recognition.whisper_adapter import get_whisper_adapter

        self._providers["whisper_api"] = get_whisper_adapter()

    @property
    def available_providers(self) -> list[str]:
        """List providers that are currently usable."""
        available = ["web_speech"]  # Always available (browser-side)
        for name, provider in self._providers.items():
            if provider.is_available:
                available.append(name)
        return available

    async def transcribe(
        self,
        audio_data: bytes,
        source: str | None = None,
        language: str = "en-US",
        user_id: str = "default",
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe audio with provider selection and fallback.

        Args:
            audio_data: Raw audio bytes.
            source: Preferred provider name (None = use config default).
            language: Language code for recognition.
            user_id: User ID for logging.
            **kwargs: Additional args passed to provider (mime_type, filename).

        Returns:
            TranscriptionResult from the first successful provider.
        """
        transcription_config = self._config.get("transcription", {})
        preferred = source or transcription_config.get(
            "default_provider", "whisper_api"
        )

        # Build fallback chain
        fallback_chain = transcription_config.get("fallback_chain", ["whisper_api"])
        providers_to_try = [preferred] + [
            p for p in fallback_chain if p != preferred
        ]

        last_error = ""
        fallback_used = False

        for i, provider_name in enumerate(providers_to_try):
            # Skip web_speech — that's browser-side only
            if provider_name == "web_speech":
                continue

            provider = self._providers.get(provider_name)
            if not provider or not provider.is_available:
                continue

            try:
                start_ms = time.monotonic()
                result = await provider.transcribe(
                    audio_data, language=language, **kwargs
                )
                elapsed_ms = int((time.monotonic() - start_ms) * 1000)

                if result.transcript:
                    fallback_used = i > 0

                    # Log transcription for accuracy tracking
                    self._log_transcription(
                        user_id=user_id,
                        provider=provider_name,
                        result=result,
                        transcription_time_ms=elapsed_ms,
                        fallback_used=fallback_used,
                    )

                    return result

                last_error = "Empty transcript returned"
            except Exception as e:
                logger.warning(
                    "Provider %s failed: %s", provider_name, e, exc_info=True
                )
                last_error = str(e)
                continue

        # All providers failed
        return TranscriptionResult(
            transcript="",
            confidence=0.0,
            source="none",
            language=language,
            is_final=True,
        )

    def _log_transcription(
        self,
        user_id: str,
        provider: str,
        result: TranscriptionResult,
        transcription_time_ms: int,
        fallback_used: bool,
    ) -> None:
        """Log transcription to voice_commands table for accuracy analysis."""
        try:
            conn = get_connection()
            conn.execute(
                """INSERT INTO voice_commands
                   (id, user_id, transcript, confidence, source,
                    audio_duration_ms, intent, parsed_successfully,
                    transcription_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    user_id,
                    result.transcript,
                    result.confidence,
                    provider,
                    result.duration_ms,
                    None,  # No intent yet — just transcription
                    True,
                    transcription_time_ms,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to log transcription: %s", e)


# Module-level singleton
_coordinator: TranscriptionCoordinator | None = None


def get_transcription_coordinator() -> TranscriptionCoordinator:
    """Get or create the global TranscriptionCoordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = TranscriptionCoordinator()
    return _coordinator
