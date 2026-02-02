"""
Channel Tools Package
Cross-platform messaging adapters and gateway for DexAI.
"""

from .models import (
    VALID_CHANNELS,
    VALID_CONTENT_TYPES,
    VALID_DIRECTIONS,
    Attachment,
    ChannelUser,
    Conversation,
    PairingCode,
    UnifiedMessage,
    validate_message,
)


__all__ = [
    "VALID_CHANNELS",
    "VALID_CONTENT_TYPES",
    "VALID_DIRECTIONS",
    "Attachment",
    "ChannelUser",
    "Conversation",
    "PairingCode",
    "UnifiedMessage",
    "validate_message",
]
