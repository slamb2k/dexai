"""Voice recognition providers."""

from tools.voice.recognition.base import BaseTranscriber
from tools.voice.recognition.web_speech_config import (
    WebSpeechConfig,
    process_web_speech_result,
)

__all__ = [
    "BaseTranscriber",
    "WebSpeechConfig",
    "process_web_speech_result",
]
