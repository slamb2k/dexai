"""
Tool: Office Models
Purpose: Data structures for office integration (email, calendar, accounts)

Usage:
    from tools.office.models import Email, CalendarEvent, OfficeAccount, IntegrationLevel

This module provides the foundation data structures for office integration,
normalizing data across Google Workspace and Microsoft 365.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any


class IntegrationLevel(IntEnum):
    """
    Office integration levels.

    Each level unlocks additional capabilities:
    - SANDBOXED (1): Dex has own email/calendar, user forwards content
    - READ_ONLY (2): Dex can read user's inbox/calendar
    - COLLABORATIVE (3): Dex creates drafts, schedules as user
    - MANAGED_PROXY (4): Dex sends with undo, full audit
    - AUTONOMOUS (5): Policy-based automation
    """

    SANDBOXED = 1
    READ_ONLY = 2
    COLLABORATIVE = 3
    MANAGED_PROXY = 4
    AUTONOMOUS = 5

    @property
    def display_name(self) -> str:
        """Human-readable level name."""
        names = {
            1: "Sandboxed",
            2: "Read-Only",
            3: "Collaborative",
            4: "Managed Proxy",
            5: "Autonomous",
        }
        return names.get(self.value, "Unknown")

    @property
    def description(self) -> str:
        """Short description of level capabilities."""
        descriptions = {
            1: "Dex uses its own email/calendar. You forward content to share.",
            2: "Dex can read your inbox and calendar. Suggests actions but cannot act.",
            3: "Dex creates drafts and schedules meetings. You review before sending.",
            4: "Dex sends on your behalf with undo window. Full audit trail.",
            5: "Dex manages email and calendar autonomously based on your policies.",
        }
        return descriptions.get(self.value, "")

    @property
    def risk_level(self) -> str:
        """Risk assessment for this level."""
        risks = {
            1: "Very Low",
            2: "Low",
            3: "Medium",
            4: "Medium-High",
            5: "High",
        }
        return risks.get(self.value, "Unknown")


class Provider(str):
    """Office provider identifiers."""

    GOOGLE = "google"
    MICROSOFT = "microsoft"
    STANDALONE = "standalone"  # IMAP/SMTP for Level 1


@dataclass
class EmailAddress:
    """
    Email address with display name.
    """

    address: str
    name: str | None = None

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} <{self.address}>"
        return self.address

    def to_dict(self) -> dict[str, Any]:
        return {"address": self.address, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailAddress":
        return cls(**data)

    @classmethod
    def from_string(cls, s: str) -> "EmailAddress":
        """Parse 'Name <email>' or plain 'email' format."""
        import re

        match = re.match(r"^(.+?)\s*<([^>]+)>$", s.strip())
        if match:
            return cls(address=match.group(2), name=match.group(1).strip())
        return cls(address=s.strip())


@dataclass
class Email:
    """
    Normalized email message across providers.

    Represents an email from Gmail, Outlook, or standalone IMAP.
    """

    id: str
    account_id: str
    message_id: str  # Provider's message ID
    thread_id: str | None = None

    # Headers
    subject: str = ""
    sender: EmailAddress | None = None
    to: list[EmailAddress] = field(default_factory=list)
    cc: list[EmailAddress] = field(default_factory=list)
    bcc: list[EmailAddress] = field(default_factory=list)
    reply_to: EmailAddress | None = None

    # Content
    snippet: str = ""  # Preview text
    body_text: str | None = None  # Plain text body
    body_html: str | None = None  # HTML body

    # Metadata
    received_at: datetime = field(default_factory=datetime.now)
    labels: list[str] = field(default_factory=list)
    is_read: bool = False
    is_starred: bool = False
    is_draft: bool = False
    has_attachments: bool = False

    # Provider-specific
    provider: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["received_at"] = self.received_at.isoformat()
        if self.sender:
            d["sender"] = self.sender.to_dict() if isinstance(self.sender, EmailAddress) else self.sender
        d["to"] = [
            (a.to_dict() if isinstance(a, EmailAddress) else a) for a in self.to
        ]
        d["cc"] = [
            (a.to_dict() if isinstance(a, EmailAddress) else a) for a in self.cc
        ]
        d["bcc"] = [
            (a.to_dict() if isinstance(a, EmailAddress) else a) for a in self.bcc
        ]
        if self.reply_to:
            d["reply_to"] = (
                self.reply_to.to_dict()
                if isinstance(self.reply_to, EmailAddress)
                else self.reply_to
            )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Email":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("received_at"), str):
            data["received_at"] = datetime.fromisoformat(data["received_at"])
        if data.get("sender") and isinstance(data["sender"], dict):
            data["sender"] = EmailAddress.from_dict(data["sender"])
        for field_name in ["to", "cc", "bcc"]:
            if data.get(field_name):
                data[field_name] = [
                    EmailAddress.from_dict(a) if isinstance(a, dict) else a
                    for a in data[field_name]
                ]
        if data.get("reply_to") and isinstance(data["reply_to"], dict):
            data["reply_to"] = EmailAddress.from_dict(data["reply_to"])
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @staticmethod
    def generate_id() -> str:
        """Generate a new internal ID."""
        return str(uuid.uuid4())


@dataclass
class Attendee:
    """
    Calendar event attendee.
    """

    email: str
    name: str | None = None
    status: str = "needsAction"  # needsAction, accepted, declined, tentative
    is_organizer: bool = False
    is_optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attendee":
        return cls(**data)


@dataclass
class CalendarEvent:
    """
    Normalized calendar event across providers.

    Represents an event from Google Calendar, Outlook Calendar, or CalDAV.
    """

    id: str
    account_id: str
    event_id: str  # Provider's event ID
    calendar_id: str = "primary"

    # Event details
    title: str = ""
    description: str = ""
    location: str = ""

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = field(default_factory=datetime.now)
    all_day: bool = False
    timezone: str = "UTC"

    # Recurrence
    is_recurring: bool = False
    recurrence_rule: str | None = None  # RRULE format

    # Participants
    organizer: Attendee | None = None
    attendees: list[Attendee] = field(default_factory=list)

    # Status
    status: str = "confirmed"  # confirmed, tentative, cancelled
    visibility: str = "default"  # default, public, private
    busy_status: str = "busy"  # free, busy, tentative

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    # Meeting
    is_meeting: bool = False
    meeting_link: str | None = None

    # Provider-specific
    provider: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_minutes(self) -> int:
        """Get event duration in minutes."""
        if self.all_day:
            return 24 * 60
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["start_time"] = self.start_time.isoformat()
        d["end_time"] = self.end_time.isoformat()
        d["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            d["updated_at"] = self.updated_at.isoformat()
        if self.organizer:
            d["organizer"] = (
                self.organizer.to_dict()
                if isinstance(self.organizer, Attendee)
                else self.organizer
            )
        d["attendees"] = [
            (a.to_dict() if isinstance(a, Attendee) else a) for a in self.attendees
        ]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEvent":
        """Create from dict."""
        data = data.copy()
        for time_field in ["start_time", "end_time", "created_at", "updated_at"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])
        if data.get("organizer") and isinstance(data["organizer"], dict):
            data["organizer"] = Attendee.from_dict(data["organizer"])
        if data.get("attendees"):
            data["attendees"] = [
                Attendee.from_dict(a) if isinstance(a, dict) else a
                for a in data["attendees"]
            ]
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @staticmethod
    def generate_id() -> str:
        """Generate a new internal ID."""
        return str(uuid.uuid4())


@dataclass
class OfficeAccount:
    """
    Connected office account (Google, Microsoft, or standalone).

    Tracks OAuth tokens, integration level, and account metadata.
    """

    id: str
    user_id: str  # DexAI user ID
    provider: str  # 'google', 'microsoft', 'standalone'
    integration_level: IntegrationLevel = IntegrationLevel.SANDBOXED

    # Account info
    email_address: str = ""
    display_name: str = ""

    # OAuth tokens (encrypted in database)
    access_token: str | None = None
    refresh_token: str | None = None
    token_expiry: datetime | None = None
    scopes: list[str] = field(default_factory=list)

    # Status
    is_active: bool = True
    last_sync: datetime | None = None
    sync_error: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (excludes tokens)."""
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "integration_level": self.integration_level.value,
            "email_address": self.email_address,
            "display_name": self.display_name,
            "scopes": self.scopes,
            "is_active": self.is_active,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "sync_error": self.sync_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OfficeAccount":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("integration_level"), int):
            data["integration_level"] = IntegrationLevel(data["integration_level"])
        for time_field in ["token_expiry", "last_sync", "created_at", "updated_at"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])
        if isinstance(data.get("scopes"), str):
            data["scopes"] = json.loads(data["scopes"])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new account ID."""
        return str(uuid.uuid4())

    def is_token_expired(self) -> bool:
        """Check if access token has expired."""
        if not self.token_expiry:
            return True
        return datetime.now() >= self.token_expiry

    def can_read_inbox(self) -> bool:
        """Check if account can read user's inbox."""
        return self.integration_level >= IntegrationLevel.READ_ONLY

    def can_create_drafts(self) -> bool:
        """Check if account can create drafts."""
        return self.integration_level >= IntegrationLevel.COLLABORATIVE

    def can_send_email(self) -> bool:
        """Check if account can send email."""
        return self.integration_level >= IntegrationLevel.MANAGED_PROXY

    def can_act_autonomously(self) -> bool:
        """Check if account can take autonomous actions."""
        return self.integration_level >= IntegrationLevel.AUTONOMOUS


@dataclass
class OfficeAction:
    """
    Queued office action (for Level 4+ undo capability).

    Actions are queued with an undo deadline. If not undone within
    the window, the action is executed.
    """

    id: str
    account_id: str
    action_type: str  # 'send_email', 'delete_email', 'schedule_meeting', etc.
    action_data: dict[str, Any] = field(default_factory=dict)

    # Status
    status: str = "pending"  # pending, executed, undone, expired, failed
    undo_deadline: datetime | None = None
    executed_at: datetime | None = None
    error_message: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["action_data"] = json.dumps(self.action_data)
        if self.undo_deadline:
            d["undo_deadline"] = self.undo_deadline.isoformat()
        if self.executed_at:
            d["executed_at"] = self.executed_at.isoformat()
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OfficeAction":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("action_data"), str):
            data["action_data"] = json.loads(data["action_data"])
        for time_field in ["undo_deadline", "executed_at", "created_at"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new action ID."""
        return str(uuid.uuid4())

    def can_undo(self) -> bool:
        """Check if action can still be undone."""
        if self.status != "pending":
            return False
        if not self.undo_deadline:
            return False
        return datetime.now() < self.undo_deadline


# Valid values for validation
VALID_PROVIDERS = {"google", "microsoft", "standalone"}
VALID_ACTION_TYPES = {
    "send_email",
    "delete_email",
    "archive_email",
    "mark_read",
    "mark_unread",
    "star_email",
    "unstar_email",
    "create_draft",
    "update_draft",
    "delete_draft",
    "schedule_meeting",
    "update_meeting",
    "cancel_meeting",
    "accept_meeting",
    "decline_meeting",
    "tentative_meeting",
}
VALID_ACTION_STATUSES = {"pending", "executed", "undone", "expired", "failed"}
VALID_EVENT_STATUSES = {"confirmed", "tentative", "cancelled"}
VALID_ATTENDEE_STATUSES = {"needsAction", "accepted", "declined", "tentative"}


if __name__ == "__main__":
    # Self-test
    import sys

    print("Testing office models...")

    # Test IntegrationLevel
    level = IntegrationLevel.COLLABORATIVE
    assert level.display_name == "Collaborative"
    assert level.value == 3
    assert IntegrationLevel.READ_ONLY < IntegrationLevel.MANAGED_PROXY

    # Test EmailAddress
    addr = EmailAddress(address="test@example.com", name="Test User")
    assert str(addr) == "Test User <test@example.com>"
    addr2 = EmailAddress.from_string("John Doe <john@example.com>")
    assert addr2.name == "John Doe"
    assert addr2.address == "john@example.com"

    # Test Email round-trip
    email = Email(
        id=Email.generate_id(),
        account_id="acc-1",
        message_id="msg-1",
        subject="Test Email",
        sender=EmailAddress(address="sender@test.com", name="Sender"),
        to=[EmailAddress(address="recipient@test.com")],
        snippet="This is a test...",
    )
    d = email.to_dict()
    email2 = Email.from_dict(d)
    assert email.subject == email2.subject
    assert email.sender.address == email2.sender.address

    # Test CalendarEvent round-trip
    event = CalendarEvent(
        id=CalendarEvent.generate_id(),
        account_id="acc-1",
        event_id="evt-1",
        title="Team Meeting",
        start_time=datetime.now(),
        end_time=datetime.now(),
        attendees=[
            Attendee(email="user@test.com", name="User", status="accepted"),
        ],
    )
    d = event.to_dict()
    event2 = CalendarEvent.from_dict(d)
    assert event.title == event2.title
    assert len(event2.attendees) == 1

    # Test OfficeAccount
    account = OfficeAccount(
        id=OfficeAccount.generate_id(),
        user_id="user-1",
        provider="google",
        integration_level=IntegrationLevel.READ_ONLY,
        email_address="user@gmail.com",
        scopes=["gmail.readonly", "calendar.readonly"],
    )
    assert account.can_read_inbox()
    assert not account.can_create_drafts()
    assert not account.can_send_email()

    account.integration_level = IntegrationLevel.MANAGED_PROXY
    assert account.can_send_email()
    assert not account.can_act_autonomously()

    # Test OfficeAction
    action = OfficeAction(
        id=OfficeAction.generate_id(),
        account_id="acc-1",
        action_type="send_email",
        action_data={"to": "test@test.com", "subject": "Hello"},
        undo_deadline=datetime.now(),
    )
    d = action.to_dict()
    action2 = OfficeAction.from_dict(d)
    assert action.action_type == action2.action_type
    assert action2.action_data["to"] == "test@test.com"

    print("OK: All office model tests passed")
    sys.exit(0)
