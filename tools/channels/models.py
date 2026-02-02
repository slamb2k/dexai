"""
Tool: Message Models
Purpose: Canonical data structures for cross-platform messaging

Usage:
    from tools.channels.models import UnifiedMessage, Attachment, ChannelUser, Conversation

This module provides the foundation data structures that normalize messages
across different platforms (Telegram, Discord, Slack) into a common format.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
import uuid


@dataclass
class Attachment:
    """
    File attachment in a message.

    Normalizes attachments from different platforms:
    - Telegram: photos, voice notes, documents
    - Discord: attachments, embeds
    - Slack: files, images
    """
    id: str
    type: str                    # 'image' | 'audio' | 'video' | 'document'
    filename: str
    mime_type: str
    size_bytes: int
    url: Optional[str] = None
    local_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Attachment':
        """Create from dict."""
        return cls(**data)


@dataclass
class UnifiedMessage:
    """
    Normalized message format across all channels.

    This is the canonical message format used throughout the system.
    Channel adapters convert platform-specific messages to/from this format.

    Attributes:
        id: Internal message UUID
        channel: Platform name (telegram | discord | slack | whatsapp)
        channel_message_id: Platform-specific message ID
        user_id: Our internal user ID (resolved by router)
        channel_user_id: Platform-specific user ID
        direction: Message direction ('inbound' | 'outbound')
        content: Text content of the message
        content_type: Type of content ('text' | 'voice' | 'image' | 'document')
        attachments: List of file attachments
        reply_to: ID of message being replied to (if any)
        timestamp: When the message was created
        session_id: Associated session ID (if any)
        metadata: Platform-specific metadata
    """
    id: str
    channel: str                 # telegram | discord | slack | whatsapp
    channel_message_id: str
    channel_user_id: str         # Platform-specific user ID
    direction: str               # 'inbound' | 'outbound'
    content: str
    user_id: Optional[str] = None  # Our user ID (resolved by router)
    content_type: str = 'text'   # 'text' | 'voice' | 'image' | 'document'
    attachments: List[Attachment] = field(default_factory=list)
    reply_to: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        # Convert attachments to dicts
        d['attachments'] = [a if isinstance(a, dict) else asdict(a) for a in self.attachments]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedMessage':
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if data.get('attachments'):
            data['attachments'] = [
                Attachment(**a) if isinstance(a, dict) else a
                for a in data['attachments']
            ]
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'UnifiedMessage':
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @staticmethod
    def generate_id() -> str:
        """Generate a new message ID."""
        return str(uuid.uuid4())


@dataclass
class ChannelUser:
    """
    Normalized user across channels.

    Represents a user identity on a specific channel. Multiple ChannelUser
    records can be linked to a single internal user via identity linking.

    Attributes:
        id: Our internal user ID
        channel: Platform name
        channel_user_id: Platform-specific user ID
        display_name: User's display name
        username: Platform username (if available)
        is_paired: Whether user has completed pairing
        first_seen: When user was first seen
        metadata: Platform-specific user data
    """
    id: str                      # Our internal user ID
    channel: str
    channel_user_id: str
    display_name: str
    username: Optional[str] = None
    is_paired: bool = False
    first_seen: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['first_seen'] = self.first_seen.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelUser':
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get('first_seen'), str):
            data['first_seen'] = datetime.fromisoformat(data['first_seen'])
        # Handle boolean from SQLite (stored as int)
        if 'is_paired' in data:
            data['is_paired'] = bool(data['is_paired'])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new user ID."""
        return str(uuid.uuid4())


@dataclass
class Conversation:
    """
    Conversation thread context.

    Represents a conversation context which could be:
    - Direct message thread
    - Group chat
    - Channel/forum thread

    Attributes:
        id: Our internal conversation ID
        channel: Platform name
        channel_conversation_id: Platform-specific conversation ID
        conversation_type: Type of conversation ('dm' | 'group' | 'channel' | 'thread')
        participants: List of user IDs in the conversation
        created_at: When conversation started
        last_message_at: Timestamp of most recent message
    """
    id: str
    channel: str
    channel_conversation_id: str
    conversation_type: str       # 'dm' | 'group' | 'channel' | 'thread'
    participants: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_message_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat()
        if self.last_message_at:
            d['last_message_at'] = self.last_message_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('last_message_at'), str):
            data['last_message_at'] = datetime.fromisoformat(data['last_message_at'])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new conversation ID."""
        return str(uuid.uuid4())


@dataclass
class PairingCode:
    """
    Temporary pairing code for cross-channel identity linking.

    When a user wants to link their account across channels, they generate
    a pairing code on one channel and enter it on another to link identities.
    """
    code: str
    user_id: str
    channel: str
    channel_user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat()
        if self.expires_at:
            d['expires_at'] = self.expires_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PairingCode':
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('expires_at'), str):
            data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        if 'used' in data:
            data['used'] = bool(data['used'])
        return cls(**data)

    def is_expired(self) -> bool:
        """Check if the pairing code has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the pairing code is still valid (not used, not expired)."""
        return not self.used and not self.is_expired()


# Type aliases for clarity
ChannelName = str  # 'telegram' | 'discord' | 'slack' | 'whatsapp'
Direction = str    # 'inbound' | 'outbound'
ContentType = str  # 'text' | 'voice' | 'image' | 'document'
ConversationType = str  # 'dm' | 'group' | 'channel' | 'thread'

# Valid values
VALID_CHANNELS = {'telegram', 'discord', 'slack', 'whatsapp', 'api', 'cli'}
VALID_DIRECTIONS = {'inbound', 'outbound'}
VALID_CONTENT_TYPES = {'text', 'voice', 'image', 'document', 'video'}
VALID_CONVERSATION_TYPES = {'dm', 'group', 'channel', 'thread'}
VALID_ATTACHMENT_TYPES = {'image', 'audio', 'video', 'document'}


def validate_message(message: UnifiedMessage) -> tuple[bool, str]:
    """
    Validate a UnifiedMessage has required fields and valid values.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not message.id:
        return False, "Message ID required"
    if message.channel not in VALID_CHANNELS:
        return False, f"Invalid channel: {message.channel}"
    if message.direction not in VALID_DIRECTIONS:
        return False, f"Invalid direction: {message.direction}"
    if message.content_type not in VALID_CONTENT_TYPES:
        return False, f"Invalid content_type: {message.content_type}"
    if not message.channel_user_id:
        return False, "channel_user_id required"
    return True, ""


if __name__ == '__main__':
    # Self-test
    import sys

    print("Testing message models...")

    # Test UnifiedMessage
    msg = UnifiedMessage(
        id='test-1',
        channel='telegram',
        channel_message_id='123',
        user_id='alice',
        channel_user_id='tg_123',
        direction='inbound',
        content='Hello world',
        content_type='text'
    )

    # Test serialization round-trip
    d = msg.to_dict()
    msg2 = UnifiedMessage.from_dict(d)
    assert msg.content == msg2.content, "Round-trip failed"
    assert msg.id == msg2.id, "ID mismatch"

    # Test JSON round-trip
    json_str = msg.to_json()
    msg3 = UnifiedMessage.from_json(json_str)
    assert msg.content == msg3.content, "JSON round-trip failed"

    # Test with attachment
    attach = Attachment(
        id='file-1',
        type='image',
        filename='photo.jpg',
        mime_type='image/jpeg',
        size_bytes=1024
    )
    msg_with_attach = UnifiedMessage(
        id='test-2',
        channel='discord',
        channel_message_id='456',
        channel_user_id='dc_456',
        direction='inbound',
        content='Check this out',
        attachments=[attach]
    )
    d = msg_with_attach.to_dict()
    msg4 = UnifiedMessage.from_dict(d)
    assert len(msg4.attachments) == 1, "Attachment lost"
    assert msg4.attachments[0].filename == 'photo.jpg', "Attachment data wrong"

    # Test ChannelUser
    user = ChannelUser(
        id='user-1',
        channel='telegram',
        channel_user_id='tg_123',
        display_name='Alice',
        username='alice_bot'
    )
    d = user.to_dict()
    user2 = ChannelUser.from_dict(d)
    assert user.display_name == user2.display_name, "User round-trip failed"

    # Test Conversation
    conv = Conversation(
        id='conv-1',
        channel='slack',
        channel_conversation_id='C123456',
        conversation_type='channel',
        participants=['user-1', 'user-2']
    )
    d = conv.to_dict()
    conv2 = Conversation.from_dict(d)
    assert len(conv2.participants) == 2, "Conversation round-trip failed"

    # Test PairingCode
    from datetime import timedelta
    code = PairingCode(
        code='ABC12345',
        user_id='user-1',
        channel='telegram',
        channel_user_id='tg_123',
        expires_at=datetime.now() + timedelta(minutes=10)
    )
    assert code.is_valid(), "New code should be valid"

    expired_code = PairingCode(
        code='EXPIRED1',
        user_id='user-2',
        channel='discord',
        channel_user_id='dc_456',
        expires_at=datetime.now() - timedelta(minutes=1)
    )
    assert not expired_code.is_valid(), "Expired code should be invalid"

    # Test validation
    valid, error = validate_message(msg)
    assert valid, f"Valid message failed validation: {error}"

    invalid_msg = UnifiedMessage(
        id='test-3',
        channel='invalid_channel',
        channel_message_id='789',
        channel_user_id='xyz',
        direction='inbound',
        content='Test'
    )
    valid, error = validate_message(invalid_msg)
    assert not valid, "Invalid message should fail validation"

    print("OK: All model tests passed")
    print(f"\nSample message JSON:\n{json.dumps(d, indent=2)}")
    sys.exit(0)
