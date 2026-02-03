"""Office Policies — Policy Engine for Level 5 Autonomous Integration

This module provides the policy system for Autonomous (Level 5) integration.
Policies define rules for automated email and calendar management, allowing
Dex to act on the user's behalf based on configurable conditions.

Philosophy:
    ADHD users benefit from automation that reduces cognitive load. Policies
    encode user preferences into executable rules, handling routine tasks
    automatically while preserving user control through VIP lists, emergency
    pauses, and undo capabilities.

Components:
    __init__.py: Policy types, conditions, actions, and database schema
    matcher.py: Condition matching engine for events
    executor.py: Policy execution engine (future)
    templates.py: Response template management (future)

Policy Types:
    INBOX: Email filtering and automatic actions (archive, label, auto-reply)
    CALENDAR: Meeting management (auto-accept, decline, suggest alternatives)
    RESPONSE: Auto-reply rules based on sender, content, time
    SCHEDULE: Time-based automation (focus mode, digest scheduling)

Safety Features:
    - VIP contacts bypass automation and always notify
    - Emergency pause stops all autonomous actions
    - Daily execution limits prevent runaway automation
    - Cooldown periods between repeated actions
    - Undo windows for reversible actions
"""

import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office import DB_PATH, PROJECT_ROOT, get_connection


# Re-export path constants from parent
__all__ = [
    "PROJECT_ROOT",
    "DB_PATH",
    "PolicyType",
    "ConditionOperator",
    "ActionType",
    "PolicyCondition",
    "PolicyAction",
    "Policy",
    "ResponseTemplate",
    "VIPContact",
    "EmergencyState",
    "get_connection",
    "ensure_policy_tables",
]


class PolicyType(str, Enum):
    """
    Types of automation policies.

    Each type targets a specific domain of office automation:
    - INBOX: Email filtering and automatic actions
    - CALENDAR: Meeting management rules
    - RESPONSE: Auto-reply configuration
    - SCHEDULE: Time-based automation triggers
    """

    INBOX = "inbox"
    CALENDAR = "calendar"
    RESPONSE = "response"
    SCHEDULE = "schedule"

    @classmethod
    def values(cls) -> set[str]:
        """Get all policy type values as a set."""
        return {item.value for item in cls}


class ConditionOperator(str, Enum):
    """
    Operators for policy condition matching.

    Conditions compare a field value against an expected value using
    these operators. Some operators (IS_EMPTY, IN_VIP_LIST) ignore
    the comparison value.
    """

    EQUALS = "equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_REGEX = "matches_regex"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"
    IS_EMPTY = "is_empty"
    IN_VIP_LIST = "in_vip_list"

    @classmethod
    def values(cls) -> set[str]:
        """Get all operator values as a set."""
        return {item.value for item in cls}


class ActionType(str, Enum):
    """
    Actions that can be taken by policies.

    Actions are grouped by category:
    - Email: archive, delete, mark_read, star, label, forward, auto_reply
    - Calendar: accept, decline, tentative, suggest_alternative
    - Notification: notify_immediately, notify_digest, suppress
    - Special: ignore_flow_state, escalate
    """

    # Email actions
    ARCHIVE = "archive"
    DELETE = "delete"
    MARK_READ = "mark_read"
    STAR = "star"
    LABEL = "label"
    FORWARD = "forward"
    AUTO_REPLY = "auto_reply"

    # Calendar actions
    ACCEPT = "accept"
    DECLINE = "decline"
    TENTATIVE = "tentative"
    SUGGEST_ALTERNATIVE = "suggest_alternative"

    # Notification actions
    NOTIFY_IMMEDIATELY = "notify_immediately"
    NOTIFY_DIGEST = "notify_digest"
    SUPPRESS_NOTIFICATION = "suppress"

    # Special actions
    IGNORE_FLOW_STATE = "ignore_flow_state"
    ESCALATE_TO_USER = "escalate"

    @classmethod
    def values(cls) -> set[str]:
        """Get all action type values as a set."""
        return {item.value for item in cls}

    @property
    def category(self) -> str:
        """Get the category for this action type."""
        email_actions = {
            "archive",
            "delete",
            "mark_read",
            "star",
            "label",
            "forward",
            "auto_reply",
        }
        calendar_actions = {"accept", "decline", "tentative", "suggest_alternative"}
        notification_actions = {"notify_immediately", "notify_digest", "suppress"}

        if self.value in email_actions:
            return "email"
        if self.value in calendar_actions:
            return "calendar"
        if self.value in notification_actions:
            return "notification"
        return "special"

    @property
    def is_destructive(self) -> bool:
        """Check if this action is destructive (harder to undo)."""
        return self.value in {"delete", "forward"}

    @property
    def requires_parameters(self) -> bool:
        """Check if this action requires additional parameters."""
        return self.value in {
            "label",
            "forward",
            "auto_reply",
            "suggest_alternative",
        }


@dataclass
class PolicyCondition:
    """
    A single condition in a policy rule.

    Conditions specify a field to check, an operator, and a value to compare.
    Multiple conditions in a policy are ANDed together.

    Attributes:
        field: The event field to check (e.g., "from_domain", "subject")
        operator: How to compare the field value
        value: The expected value (ignored for IS_EMPTY, IN_VIP_LIST)
    """

    field: str
    operator: ConditionOperator
    value: Any

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "field": self.field,
            "operator": (
                self.operator.value
                if isinstance(self.operator, ConditionOperator)
                else self.operator
            ),
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyCondition":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("operator"), str):
            data["operator"] = ConditionOperator(data["operator"])
        return cls(**data)


@dataclass
class PolicyAction:
    """
    An action to take when policy conditions match.

    Actions specify what to do and any required parameters.

    Attributes:
        action_type: The type of action to perform
        parameters: Action-specific parameters (e.g., label name, forward address)
    """

    action_type: ActionType
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "action_type": (
                self.action_type.value
                if isinstance(self.action_type, ActionType)
                else self.action_type
            ),
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyAction":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("action_type"), str):
            data["action_type"] = ActionType(data["action_type"])
        return cls(**data)


@dataclass
class Policy:
    """
    A complete automation policy.

    Policies combine conditions (what to match) with actions (what to do).
    When an event matches all conditions, all actions are executed.

    Attributes:
        id: Unique policy identifier
        account_id: The office account this policy belongs to
        name: Human-readable policy name
        description: Detailed description of what this policy does
        policy_type: Category of policy (inbox, calendar, response, schedule)
        conditions: List of conditions that must ALL match
        actions: List of actions to take when conditions match
        enabled: Whether this policy is active
        priority: Higher priority policies are evaluated first
        created_at: When the policy was created
        updated_at: When the policy was last modified
        max_executions_per_day: Limit on daily executions (None = unlimited)
        cooldown_minutes: Minimum time between executions (None = no cooldown)
        require_undo_window: Whether actions should have undo capability
    """

    id: str
    account_id: str
    name: str
    description: str
    policy_type: PolicyType
    conditions: list[PolicyCondition]
    actions: list[PolicyAction]
    enabled: bool = True
    priority: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    max_executions_per_day: int | None = None
    cooldown_minutes: int | None = None
    require_undo_window: bool = True

    def __post_init__(self) -> None:
        """Set default timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "description": self.description,
            "policy_type": (
                self.policy_type.value
                if isinstance(self.policy_type, PolicyType)
                else self.policy_type
            ),
            "conditions": [c.to_dict() for c in self.conditions],
            "actions": [a.to_dict() for a in self.actions],
            "enabled": self.enabled,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "max_executions_per_day": self.max_executions_per_day,
            "cooldown_minutes": self.cooldown_minutes,
            "require_undo_window": self.require_undo_window,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        """Create from dict."""
        data = data.copy()

        if isinstance(data.get("policy_type"), str):
            data["policy_type"] = PolicyType(data["policy_type"])

        if data.get("conditions"):
            if isinstance(data["conditions"], str):
                data["conditions"] = json.loads(data["conditions"])
            data["conditions"] = [
                PolicyCondition.from_dict(c) if isinstance(c, dict) else c
                for c in data["conditions"]
            ]

        if data.get("actions"):
            if isinstance(data["actions"], str):
                data["actions"] = json.loads(data["actions"])
            data["actions"] = [
                PolicyAction.from_dict(a) if isinstance(a, dict) else a
                for a in data["actions"]
            ]

        for time_field in ["created_at", "updated_at"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])

        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @staticmethod
    def generate_id() -> str:
        """Generate a new policy ID."""
        return str(uuid.uuid4())


@dataclass
class ResponseTemplate:
    """
    A reusable response template for auto-replies.

    Templates support variable substitution using {variable_name} syntax.

    Attributes:
        id: Unique template identifier
        account_id: The office account this template belongs to
        name: Human-readable template name
        subject_template: Email subject with optional variables
        body_template: Email body with optional variables
        variables: List of variable names used in templates
        use_count: Number of times this template has been used
        created_at: When the template was created
        updated_at: When the template was last modified
    """

    id: str
    account_id: str
    name: str
    subject_template: str | None
    body_template: str
    variables: list[str] = field(default_factory=list)
    use_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        """Set default timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "variables": self.variables,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResponseTemplate":
        """Create from dict."""
        data = data.copy()

        if isinstance(data.get("variables"), str):
            data["variables"] = json.loads(data["variables"])

        for time_field in ["created_at", "updated_at"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])

        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new template ID."""
        return str(uuid.uuid4())

    def render(self, variables: dict[str, str]) -> tuple[str | None, str]:
        """
        Render the template with provided variables.

        Args:
            variables: Dictionary mapping variable names to values

        Returns:
            Tuple of (rendered_subject, rendered_body)
        """
        subject = self.subject_template
        body = self.body_template

        for var_name, var_value in variables.items():
            placeholder = "{" + var_name + "}"
            if subject:
                subject = subject.replace(placeholder, var_value)
            body = body.replace(placeholder, var_value)

        return subject, body


@dataclass
class VIPContact:
    """
    A VIP contact that bypasses automation rules.

    VIP contacts always trigger notifications and bypass focus mode,
    ensuring important people can always reach the user.

    Attributes:
        id: Unique VIP contact identifier
        account_id: The office account this VIP belongs to
        email: Email address of the VIP
        name: Display name
        priority: Priority level (high, medium, low)
        always_notify: Always send immediate notifications
        bypass_focus: Bypass focus/do-not-disturb mode
        notes: Optional notes about this contact
        created_at: When the VIP was added
    """

    id: str
    account_id: str
    email: str
    name: str | None = None
    priority: str = "high"
    always_notify: bool = True
    bypass_focus: bool = True
    notes: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Set default timestamp if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "account_id": self.account_id,
            "email": self.email,
            "name": self.name,
            "priority": self.priority,
            "always_notify": self.always_notify,
            "bypass_focus": self.bypass_focus,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VIPContact":
        """Create from dict."""
        data = data.copy()
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)

    @staticmethod
    def generate_id() -> str:
        """Generate a new VIP contact ID."""
        return str(uuid.uuid4())


@dataclass
class EmergencyState:
    """
    Emergency pause state for autonomous actions.

    When paused, all autonomous policy execution stops until the pause
    is lifted or expires.

    Attributes:
        account_id: The office account this state belongs to
        is_paused: Whether autonomous actions are currently paused
        paused_at: When the pause started
        paused_until: When the pause will automatically end (None = manual resume)
        pause_reason: User-provided reason for the pause
    """

    account_id: str
    is_paused: bool = False
    paused_at: datetime | None = None
    paused_until: datetime | None = None
    pause_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "account_id": self.account_id,
            "is_paused": self.is_paused,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
            "pause_reason": self.pause_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmergencyState":
        """Create from dict."""
        data = data.copy()
        for time_field in ["paused_at", "paused_until"]:
            if isinstance(data.get(time_field), str):
                data[time_field] = datetime.fromisoformat(data[time_field])
        return cls(**data)

    def is_currently_paused(self) -> bool:
        """Check if currently in a pause state (considering expiry)."""
        if not self.is_paused:
            return False
        if self.paused_until and datetime.now() >= self.paused_until:
            return False
        return True


def ensure_policy_tables() -> None:
    """
    Create the policy-related database tables.

    Creates tables for:
    - office_policy_executions: Log of policy executions
    - office_response_templates: Reusable response templates
    - office_vip_contacts: VIP contacts that bypass automation
    - office_emergency_state: Emergency pause state

    Safe to call multiple times (uses IF NOT EXISTS).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Policy execution log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_policy_executions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_data TEXT,
            actions_taken TEXT,
            result TEXT DEFAULT 'success',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id),
            FOREIGN KEY (policy_id) REFERENCES office_policies(id)
        )
    """)

    # Response templates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_response_templates (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            name TEXT NOT NULL,
            subject_template TEXT,
            body_template TEXT NOT NULL,
            variables TEXT,
            use_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # VIP contacts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_vip_contacts (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            email TEXT NOT NULL,
            name TEXT,
            priority TEXT DEFAULT 'high',
            always_notify BOOLEAN DEFAULT TRUE,
            bypass_focus BOOLEAN DEFAULT TRUE,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id),
            UNIQUE(account_id, email)
        )
    """)

    # Emergency pause state
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_emergency_state (
            account_id TEXT PRIMARY KEY,
            is_paused BOOLEAN DEFAULT FALSE,
            paused_at DATETIME,
            paused_until DATETIME,
            pause_reason TEXT,
            FOREIGN KEY (account_id) REFERENCES office_accounts(id)
        )
    """)

    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_policy_executions_account_date
        ON office_policy_executions(account_id, created_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_policy_executions_policy
        ON office_policy_executions(policy_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_response_templates_account
        ON office_response_templates(account_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vip_contacts_account
        ON office_vip_contacts(account_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vip_contacts_email
        ON office_vip_contacts(account_id, email)
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Testing office policies module...")

    # Test PolicyType
    assert PolicyType.INBOX.value == "inbox"
    assert PolicyType.values() == {"inbox", "calendar", "response", "schedule"}

    # Test ConditionOperator
    assert ConditionOperator.EQUALS.value == "equals"
    assert ConditionOperator.IN_VIP_LIST.value == "in_vip_list"
    assert len(ConditionOperator.values()) == 11

    # Test ActionType
    assert ActionType.ARCHIVE.value == "archive"
    assert ActionType.ARCHIVE.category == "email"
    assert ActionType.ACCEPT.category == "calendar"
    assert ActionType.NOTIFY_IMMEDIATELY.category == "notification"
    assert ActionType.ESCALATE_TO_USER.category == "special"
    assert ActionType.DELETE.is_destructive
    assert not ActionType.ARCHIVE.is_destructive
    assert ActionType.LABEL.requires_parameters
    assert not ActionType.ARCHIVE.requires_parameters

    # Test PolicyCondition round-trip
    condition = PolicyCondition(
        field="from_domain",
        operator=ConditionOperator.EQUALS,
        value="example.com",
    )
    d = condition.to_dict()
    assert d["operator"] == "equals"
    condition2 = PolicyCondition.from_dict(d)
    assert condition2.field == "from_domain"
    assert condition2.operator == ConditionOperator.EQUALS

    # Test PolicyAction round-trip
    action = PolicyAction(
        action_type=ActionType.LABEL,
        parameters={"label": "Important"},
    )
    d = action.to_dict()
    assert d["action_type"] == "label"
    action2 = PolicyAction.from_dict(d)
    assert action2.action_type == ActionType.LABEL
    assert action2.parameters["label"] == "Important"

    # Test Policy round-trip
    policy = Policy(
        id=Policy.generate_id(),
        account_id="acc-1",
        name="Archive newsletters",
        description="Automatically archive newsletter emails",
        policy_type=PolicyType.INBOX,
        conditions=[
            PolicyCondition(
                field="from_domain",
                operator=ConditionOperator.IN_LIST,
                value=["newsletter.example.com", "news.example.org"],
            ),
        ],
        actions=[
            PolicyAction(action_type=ActionType.ARCHIVE),
            PolicyAction(action_type=ActionType.MARK_READ),
        ],
        priority=10,
        max_executions_per_day=100,
    )
    d = policy.to_dict()
    assert d["policy_type"] == "inbox"
    assert len(d["conditions"]) == 1
    assert len(d["actions"]) == 2
    policy2 = Policy.from_dict(d)
    assert policy2.name == "Archive newsletters"
    assert policy2.priority == 10
    assert len(policy2.conditions) == 1
    assert policy2.conditions[0].operator == ConditionOperator.IN_LIST

    # Test ResponseTemplate
    template = ResponseTemplate(
        id=ResponseTemplate.generate_id(),
        account_id="acc-1",
        name="Out of office",
        subject_template="Re: {original_subject}",
        body_template="Hi {sender_name},\n\nI'm currently out of office until {return_date}.",
        variables=["original_subject", "sender_name", "return_date"],
    )
    subject, body = template.render({
        "original_subject": "Meeting request",
        "sender_name": "John",
        "return_date": "Monday",
    })
    assert subject == "Re: Meeting request"
    assert "John" in body
    assert "Monday" in body

    # Test VIPContact
    vip = VIPContact(
        id=VIPContact.generate_id(),
        account_id="acc-1",
        email="boss@company.com",
        name="The Boss",
        priority="high",
    )
    d = vip.to_dict()
    vip2 = VIPContact.from_dict(d)
    assert vip2.email == "boss@company.com"
    assert vip2.always_notify is True

    # Test EmergencyState
    state = EmergencyState(
        account_id="acc-1",
        is_paused=True,
        paused_at=datetime.now(),
        pause_reason="Overwhelmed",
    )
    assert state.is_currently_paused()
    state.is_paused = False
    assert not state.is_currently_paused()

    # Test table creation
    ensure_policy_tables()
    print("OK: Tables created successfully")

    print("OK: All office policies tests passed")
    sys.exit(0)
