"""Web Speech API configuration and result processing.

The actual Web Speech API runs in the browser (JavaScript).
This module defines the config sent to the frontend and processes
the results sent back from the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.voice.models import TranscriptionResult


@dataclass
class WebSpeechConfig:
    """Configuration for the browser-side Web Speech API."""

    language: str = "en-US"
    continuous: bool = False
    interim_results: bool = True
    max_alternatives: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "continuous": self.continuous,
            "interimResults": self.interim_results,
            "maxAlternatives": self.max_alternatives,
        }


def process_web_speech_result(result: dict[str, Any]) -> TranscriptionResult:
    """Convert a Web Speech API result dict into a TranscriptionResult.

    Expected format from the browser:
    {
        "transcript": "add task buy groceries",
        "confidence": 0.92,
        "isFinal": true,
        "alternatives": ["add task by groceries"],
        "language": "en-US",
        "durationMs": 2300
    }
    """
    return TranscriptionResult(
        transcript=result.get("transcript", "").strip(),
        confidence=result.get("confidence", 0.0),
        source="web_speech",
        language=result.get("language", "en-US"),
        duration_ms=result.get("durationMs", 0),
        is_final=result.get("isFinal", True),
        alternatives=result.get("alternatives", []),
    )
