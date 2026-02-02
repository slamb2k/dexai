"""
Channel Tools Package
Cross-platform messaging adapters and gateway for addulting-ai.
"""

from .models import (
    UnifiedMessage,
    Attachment,
    ChannelUser,
    Conversation,
    PairingCode,
    VALID_CHANNELS,
    VALID_DIRECTIONS,
    VALID_CONTENT_TYPES,
    validate_message,
)

__all__ = [
    'UnifiedMessage',
    'Attachment',
    'ChannelUser',
    'Conversation',
    'PairingCode',
    'VALID_CHANNELS',
    'VALID_DIRECTIONS',
    'VALID_CONTENT_TYPES',
    'validate_message',
]
