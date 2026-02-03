# Phase 12d: Autonomous Office Integration (Level 5)

> **Status:** Planned
> **Prerequisites:** Phase 12c (Managed Proxy) complete, 90 days at Level 4
> **Scope:** Policy-based automation, auto-responses, intelligent scheduling, emergency controls

---

## Executive Summary

Phase 12d enables **Level 5 (Autonomous)** functionality — the highest trust level where DexAI operates independently based on user-defined policies. This level is designed for users who have built confidence through 90+ days of Level 4 usage and want Dex to handle routine email and calendar management without constant oversight.

**Key Principle:** Automation with guardrails. Policies define boundaries; Dex operates freely within them.

**ADHD Value:** Level 5 is the ultimate "set and forget" — Dex handles the executive function of email triage and calendar protection so users can focus on what matters.

---

## Progressive Trust Gate

### Requirements to Unlock Level 5

| Requirement | Rationale |
|-------------|-----------|
| 90 days at Level 4 | Build confidence in Dex's judgment |
| <5% undo rate | Dex's actions align with user intent |
| Explicit acknowledgment | User understands risks and capabilities |
| At least 50 actions executed | Sufficient history to evaluate patterns |

### Acknowledgment Flow

```
┌─────────────────────────────────────────────────────────────┐
│           Upgrade to Level 5: Autonomous Mode               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  You've been using Level 4 for 94 days with a 2% undo rate.│
│  You're ready to unlock Autonomous mode.                    │
│                                                             │
│  What this means:                                           │
│  ✓ Dex will automatically handle emails matching your       │
│    policies (archive newsletters, flag VIPs, etc.)          │
│  ✓ Dex can decline meeting requests during focus time       │
│  ✓ Dex can send templated responses without asking          │
│                                                             │
│  Safety features:                                           │
│  ✓ Emergency pause stops all automation instantly           │
│  ✓ Daily digest shows everything Dex did                    │
│  ✓ You can disable any policy anytime                       │
│  ✓ Novel situations always prompt you first                 │
│                                                             │
│  [ ] I understand Dex will take actions on my behalf        │
│  [ ] I've reviewed the default policies                     │
│  [ ] I know how to use the emergency pause                  │
│                                                             │
│         [Cancel]                    [Enable Autonomous]     │
└─────────────────────────────────────────────────────────────┘
```

---

## Current State (Phase 12c Complete)

### Already Implemented

| Component | Status |
|-----------|--------|
| Database: `office_policies` table | Ready (schema exists) |
| Model: `IntegrationLevel.AUTONOMOUS` | Ready |
| Method: `OfficeAccount.can_act_autonomously()` | Ready |
| Action queue system | Complete from Phase 12c |
| Audit logging | Complete from Phase 12c |
| Daily digest | Complete from Phase 12c |

### OAuth Scopes (Level 5 = Level 4 + Contacts)

- **Google:** `gmail.modify`, `gmail.send`, `calendar`, `contacts`
- **Microsoft:** `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Contacts.ReadWrite`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Incoming Event                            │
│    (New email, meeting request, calendar conflict, etc.)    │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Policy Engine                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Match       │→ │ Evaluate    │→ │ Execute     │         │
│  │ conditions  │  │ priority    │  │ actions     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐
│  Autonomous Action  │   │  Prompt User        │
│  (Policy matched)   │   │  (Novel situation)  │
└─────────────────────┘   └─────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Action Queue (Level 4)                    │
│           (Undo window still applies by default)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### 1. Directory Structure

```
tools/office/policies/
├── __init__.py                    # Policy types, conditions, actions
├── engine.py                      # Policy evaluation engine
├── parser.py                      # Parse policy YAML/JSON
├── matcher.py                     # Condition matching logic
├── defaults.py                    # Default policy templates
├── manager.py                     # CRUD for policies
└── validator.py                   # Validate policy definitions

tools/office/automation/
├── __init__.py                    # Automation types
├── inbox_processor.py             # Process incoming emails
├── calendar_guardian.py           # Protect calendar, auto-respond
├── auto_responder.py              # Template-based auto-responses
├── contact_manager.py             # VIP list, relationship tracking
└── emergency.py                   # Emergency pause system

tools/dashboard/backend/routes/
└── policies.py                    # Policy management API
```

---

### 2. Database Schema Additions

**File:** `tools/office/__init__.py`

Add tables for automation:

```sql
-- Policy execution log (track which policies fired)
CREATE TABLE IF NOT EXISTS office_policy_executions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    trigger_type TEXT NOT NULL,           -- 'email', 'calendar', 'schedule'
    trigger_data TEXT,                    -- JSON: what triggered the policy
    actions_taken TEXT,                   -- JSON: list of actions executed
    result TEXT DEFAULT 'success',        -- 'success', 'failed', 'skipped'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id),
    FOREIGN KEY (policy_id) REFERENCES office_policies(id)
);

-- Auto-response templates
CREATE TABLE IF NOT EXISTS office_response_templates (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    name TEXT NOT NULL,
    subject_template TEXT,
    body_template TEXT NOT NULL,
    variables TEXT,                       -- JSON: available variables
    use_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- VIP contacts (override normal policies)
CREATE TABLE IF NOT EXISTS office_vip_contacts (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    email TEXT NOT NULL,
    name TEXT,
    priority TEXT DEFAULT 'high',         -- 'critical', 'high', 'normal'
    always_notify BOOLEAN DEFAULT TRUE,
    bypass_focus BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id),
    UNIQUE(account_id, email)
);

-- Emergency pause state
CREATE TABLE IF NOT EXISTS office_emergency_state (
    account_id TEXT PRIMARY KEY,
    is_paused BOOLEAN DEFAULT FALSE,
    paused_at DATETIME,
    paused_until DATETIME,               -- NULL = manual resume required
    pause_reason TEXT,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_policy_exec_account_date
    ON office_policy_executions(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_policy_exec_policy
    ON office_policy_executions(policy_id);
CREATE INDEX IF NOT EXISTS idx_vip_account_email
    ON office_vip_contacts(account_id, email);
```

---

### 3. Policy System

#### 3.1 Policy Data Model

**File:** `tools/office/policies/__init__.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class PolicyType(str, Enum):
    """Types of automation policies."""
    INBOX = "inbox"           # Email filtering/actions
    CALENDAR = "calendar"     # Meeting management
    RESPONSE = "response"     # Auto-reply rules
    SCHEDULE = "schedule"     # Time-based automation

class ConditionOperator(str, Enum):
    """Operators for condition matching."""
    EQUALS = "equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_REGEX = "matches_regex"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"

class ActionType(str, Enum):
    """Available policy actions."""
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

@dataclass
class PolicyCondition:
    """Single condition in a policy."""
    field: str                    # e.g., "from_domain", "subject", "time_of_day"
    operator: ConditionOperator
    value: Any

@dataclass
class PolicyAction:
    """Single action in a policy."""
    action_type: ActionType
    parameters: dict[str, Any] = field(default_factory=dict)

@dataclass
class Policy:
    """Complete policy definition."""
    id: str
    account_id: str
    name: str
    description: str
    policy_type: PolicyType
    conditions: list[PolicyCondition]
    actions: list[PolicyAction]
    enabled: bool = True
    priority: int = 0            # Higher = evaluated first
    created_at: datetime = None
    updated_at: datetime = None

    # Execution constraints
    max_executions_per_day: int | None = None
    cooldown_minutes: int | None = None
    require_undo_window: bool = True
```

---

#### 3.2 Policy Engine

**File:** `tools/office/policies/engine.py`

**Purpose:** Evaluate policies against events, determine actions.

**Functions:**

```python
async def evaluate_policies(
    account_id: str,
    event_type: str,              # "email", "calendar", "schedule"
    event_data: dict[str, Any],
) -> dict[str, Any]
# Returns: {"matched_policies": list, "actions": list, "should_prompt": bool}

async def execute_policy_actions(
    account_id: str,
    policy_id: str,
    actions: list[PolicyAction],
    event_data: dict[str, Any],
) -> dict[str, Any]
# Returns: {"success": True, "results": list}

def check_policy_constraints(
    policy: Policy,
    account_id: str,
) -> dict[str, Any]
# Check rate limits, cooldowns
# Returns: {"can_execute": bool, "reason": str | None}

async def get_applicable_policies(
    account_id: str,
    event_type: str,
) -> list[Policy]
# Returns enabled policies for event type, sorted by priority
```

**Evaluation Flow:**
1. Get all enabled policies for event type
2. Sort by priority (highest first)
3. For each policy, check all conditions
4. First matching policy wins (or configurable: all matching)
5. Check execution constraints
6. Return actions to execute

---

#### 3.3 Condition Matcher

**File:** `tools/office/policies/matcher.py`

**Purpose:** Match conditions against event data.

**Functions:**

```python
def match_condition(
    condition: PolicyCondition,
    event_data: dict[str, Any],
) -> bool
# Returns True if condition matches

def match_all_conditions(
    conditions: list[PolicyCondition],
    event_data: dict[str, Any],
) -> bool
# Returns True if ALL conditions match (AND logic)

def extract_field_value(
    field: str,
    event_data: dict[str, Any],
) -> Any
# Extract field value, supporting nested paths ("sender.domain")
```

**Available Fields for Matching:**

| Event Type | Field | Description |
|------------|-------|-------------|
| email | `from_address` | Sender email address |
| email | `from_domain` | Sender domain |
| email | `from_name` | Sender display name |
| email | `to_count` | Number of recipients |
| email | `cc_count` | Number of CC recipients |
| email | `subject` | Email subject |
| email | `body` | Email body text |
| email | `has_attachments` | Boolean |
| email | `is_reply` | Boolean |
| email | `is_forward` | Boolean |
| email | `labels` | List of labels |
| email | `age_hours` | Hours since received |
| calendar | `organizer` | Meeting organizer email |
| calendar | `attendee_count` | Number of attendees |
| calendar | `duration_minutes` | Meeting length |
| calendar | `is_recurring` | Boolean |
| calendar | `time_of_day` | "morning", "afternoon", "evening" |
| calendar | `day_of_week` | "monday", "tuesday", etc. |
| calendar | `conflicts_with` | List of conflicting events |
| any | `current_flow_state` | "focus", "available", "unknown" |

---

#### 3.4 Default Policies

**File:** `tools/office/policies/defaults.py`

**Purpose:** Provide sensible default policies users can enable.

```python
DEFAULT_POLICIES = [
    {
        "name": "Archive Old Newsletters",
        "description": "Auto-archive unread newsletters after 7 days",
        "policy_type": "inbox",
        "conditions": [
            {"field": "from_domain", "operator": "in_list", "value": [
                "substack.com", "mailchimp.com", "convertkit.com",
                "buttondown.email", "beehiiv.com"
            ]},
            {"field": "is_read", "operator": "equals", "value": False},
            {"field": "age_hours", "operator": "greater_than", "value": 168}
        ],
        "actions": [
            {"action_type": "archive"}
        ],
        "priority": 10
    },
    {
        "name": "VIP Immediate Notify",
        "description": "Always notify immediately for VIP contacts",
        "policy_type": "inbox",
        "conditions": [
            {"field": "from_address", "operator": "in_vip_list", "value": True}
        ],
        "actions": [
            {"action_type": "notify_immediately"},
            {"action_type": "ignore_flow_state"},
            {"action_type": "star"}
        ],
        "priority": 100
    },
    {
        "name": "Protect Focus Time",
        "description": "Auto-decline meetings during focus blocks",
        "policy_type": "calendar",
        "conditions": [
            {"field": "conflicts_with", "operator": "contains_type", "value": "focus_block"},
            {"field": "organizer", "operator": "not_in_vip_list", "value": True}
        ],
        "actions": [
            {"action_type": "decline"},
            {"action_type": "suggest_alternative", "parameters": {"days_ahead": 7}}
        ],
        "priority": 50
    },
    {
        "name": "Auto-Accept Team Meetings",
        "description": "Auto-accept recurring team meetings",
        "policy_type": "calendar",
        "conditions": [
            {"field": "organizer_domain", "operator": "equals", "value": "$user_domain"},
            {"field": "is_recurring", "operator": "equals", "value": True},
            {"field": "conflicts_with", "operator": "is_empty", "value": True}
        ],
        "actions": [
            {"action_type": "accept"}
        ],
        "priority": 30
    },
    {
        "name": "Vacation Auto-Reply",
        "description": "Send vacation response (disabled by default)",
        "policy_type": "response",
        "conditions": [
            {"field": "is_first_contact_today", "operator": "equals", "value": True}
        ],
        "actions": [
            {"action_type": "auto_reply", "parameters": {"template": "vacation"}}
        ],
        "enabled": False,
        "priority": 100
    }
]
```

---

#### 3.5 Policy Manager

**File:** `tools/office/policies/manager.py`

**Purpose:** CRUD operations for policies.

**Functions:**

```python
async def create_policy(
    account_id: str,
    name: str,
    policy_type: str,
    conditions: list[dict],
    actions: list[dict],
    description: str = "",
    priority: int = 0,
    enabled: bool = True,
) -> dict[str, Any]
# Returns: {"success": True, "policy_id": str}

async def get_policy(policy_id: str) -> dict[str, Any]

async def update_policy(policy_id: str, **updates) -> dict[str, Any]

async def delete_policy(policy_id: str) -> dict[str, Any]

async def list_policies(
    account_id: str,
    policy_type: str | None = None,
    enabled_only: bool = False,
) -> dict[str, Any]

async def toggle_policy(policy_id: str, enabled: bool) -> dict[str, Any]

async def import_default_policies(account_id: str) -> dict[str, Any]
# Import all default policies (disabled by default)

async def duplicate_policy(policy_id: str, new_name: str) -> dict[str, Any]

async def get_policy_stats(policy_id: str) -> dict[str, Any]
# Returns execution count, last execution, success rate
```

**CLI Interface:**
```bash
python tools/office/policies/manager.py --account-id <id> --list
python tools/office/policies/manager.py --account-id <id> --create --name "My Policy" --type inbox --file policy.yaml
python tools/office/policies/manager.py --account-id <id> --toggle <policy-id> --enabled true
python tools/office/policies/manager.py --account-id <id> --import-defaults
python tools/office/policies/manager.py --account-id <id> --stats <policy-id>
```

---

### 4. Automation Components

#### 4.1 Inbox Processor

**File:** `tools/office/automation/inbox_processor.py`

**Purpose:** Process incoming emails against policies.

**Functions:**

```python
async def process_email(
    account_id: str,
    email: Email,
) -> dict[str, Any]
# Evaluate policies, execute actions
# Returns: {"processed": True, "actions_taken": list, "policy_id": str | None}

async def process_inbox_batch(
    account_id: str,
    since: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]
# Process multiple emails
# Returns: {"processed": int, "actions": int, "skipped": int}

async def start_inbox_watcher(account_id: str) -> None
# Background task: watch for new emails, process automatically

async def stop_inbox_watcher(account_id: str) -> None
```

**Processing Flow:**
1. New email arrives (via webhook or polling)
2. Check emergency pause status
3. Check if sender is VIP (special handling)
4. Evaluate inbox policies
5. Execute matching actions via action queue
6. Log policy execution

---

#### 4.2 Calendar Guardian

**File:** `tools/office/automation/calendar_guardian.py`

**Purpose:** Protect calendar, auto-respond to meeting requests.

**Functions:**

```python
async def process_meeting_request(
    account_id: str,
    event: CalendarEvent,
) -> dict[str, Any]
# Evaluate calendar policies
# Returns: {"action": "accept"|"decline"|"tentative"|"prompt", "reason": str}

async def protect_focus_blocks(
    account_id: str,
) -> dict[str, Any]
# Scan calendar for conflicts with focus blocks, suggest resolutions
# Returns: {"conflicts": list, "suggestions": list}

async def suggest_meeting_alternatives(
    account_id: str,
    declined_event: CalendarEvent,
    days_ahead: int = 7,
) -> dict[str, Any]
# Find alternative times when declining
# Returns: {"alternatives": list[TimeSlot]}

async def auto_respond_to_meeting(
    account_id: str,
    event_id: str,
    response: str,  # "accept", "decline", "tentative"
    message: str | None = None,
) -> dict[str, Any]
```

---

#### 4.3 Auto-Responder

**File:** `tools/office/automation/auto_responder.py`

**Purpose:** Send templated automatic responses.

**Functions:**

```python
async def send_auto_reply(
    account_id: str,
    to_email: Email,
    template_id: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]
# Returns: {"success": True, "action_id": str}

async def create_template(
    account_id: str,
    name: str,
    body_template: str,
    subject_template: str | None = None,
    variables: list[str] | None = None,
) -> dict[str, Any]

async def get_template(template_id: str) -> dict[str, Any]

async def list_templates(account_id: str) -> dict[str, Any]

async def render_template(
    template_id: str,
    variables: dict[str, Any],
) -> dict[str, Any]
# Returns: {"subject": str, "body": str}
```

**Template Variables:**
```
{{sender_name}} - Sender's display name
{{sender_email}} - Sender's email address
{{original_subject}} - Original email subject
{{current_date}} - Today's date
{{return_date}} - Return date (for vacation)
{{user_name}} - User's display name
```

**Example Templates:**
```yaml
vacation:
  subject: "Out of Office: {{original_subject}}"
  body: |
    Hi {{sender_name}},

    Thanks for your email. I'm currently out of the office and will return on {{return_date}}.

    I'll respond to your message when I'm back. If this is urgent, please contact [backup contact].

    Best,
    {{user_name}}

acknowledged:
  subject: "Re: {{original_subject}}"
  body: |
    Hi {{sender_name}},

    Got it, thanks! I'll take a look and get back to you soon.

    {{user_name}}
```

---

#### 4.4 VIP Contact Manager

**File:** `tools/office/automation/contact_manager.py`

**Purpose:** Manage VIP contacts who bypass normal policies.

**Functions:**

```python
async def add_vip(
    account_id: str,
    email: str,
    name: str | None = None,
    priority: str = "high",
    always_notify: bool = True,
    bypass_focus: bool = True,
    notes: str | None = None,
) -> dict[str, Any]

async def remove_vip(account_id: str, email: str) -> dict[str, Any]

async def list_vips(account_id: str) -> dict[str, Any]

async def is_vip(account_id: str, email: str) -> bool

async def get_vip_settings(account_id: str, email: str) -> dict[str, Any]

async def suggest_vips(account_id: str) -> dict[str, Any]
# Analyze email history, suggest frequent/important contacts
# Returns: {"suggestions": list[{email, reason, interaction_count}]}
```

**CLI Interface:**
```bash
python tools/office/automation/contact_manager.py --account-id <id> --add-vip "boss@company.com" --name "My Boss" --priority critical
python tools/office/automation/contact_manager.py --account-id <id> --list-vips
python tools/office/automation/contact_manager.py --account-id <id> --suggest-vips
```

---

#### 4.5 Emergency Pause System

**File:** `tools/office/automation/emergency.py`

**Purpose:** Instantly stop all autonomous actions.

**Functions:**

```python
async def emergency_pause(
    account_id: str,
    reason: str = "User requested",
    duration_hours: int | None = None,  # None = until manual resume
) -> dict[str, Any]
# Returns: {"success": True, "paused_until": str | None}

async def resume_automation(account_id: str) -> dict[str, Any]
# Returns: {"success": True, "paused_duration": str}

async def get_pause_status(account_id: str) -> dict[str, Any]
# Returns: {"is_paused": bool, "paused_at": str, "paused_until": str, "reason": str}

async def schedule_pause(
    account_id: str,
    start_time: datetime,
    end_time: datetime,
    reason: str = "Scheduled pause",
) -> dict[str, Any]
# Pre-schedule a pause period

async def check_pause_status(account_id: str) -> bool
# Quick check if automation is paused
```

**Emergency Triggers:**
- Dashboard "Emergency Stop" button (big, red, always visible)
- Channel command: `!pause` or `!stop dex`
- Keyboard shortcut in dashboard: `Ctrl+Shift+P`
- API endpoint for external integrations

**When Paused:**
- No new policy executions
- Pending actions in queue continue (already committed)
- User notified via all channels
- Dashboard shows prominent "PAUSED" indicator
- Daily digest sent even when paused (shows pause status)

---

### 5. Dashboard Backend Routes

**File:** `tools/dashboard/backend/routes/policies.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/policies` | List all policies |
| GET | `/api/policies/{id}` | Get policy details |
| POST | `/api/policies` | Create new policy |
| PUT | `/api/policies/{id}` | Update policy |
| DELETE | `/api/policies/{id}` | Delete policy |
| POST | `/api/policies/{id}/toggle` | Enable/disable policy |
| POST | `/api/policies/import-defaults` | Import default policies |
| GET | `/api/policies/{id}/stats` | Get policy execution stats |
| GET | `/api/policies/executions` | List policy executions |
| GET | `/api/templates` | List response templates |
| POST | `/api/templates` | Create template |
| PUT | `/api/templates/{id}` | Update template |
| DELETE | `/api/templates/{id}` | Delete template |
| POST | `/api/templates/{id}/preview` | Preview rendered template |
| GET | `/api/vips` | List VIP contacts |
| POST | `/api/vips` | Add VIP contact |
| DELETE | `/api/vips/{email}` | Remove VIP contact |
| GET | `/api/vips/suggest` | Get VIP suggestions |
| POST | `/api/emergency/pause` | Trigger emergency pause |
| POST | `/api/emergency/resume` | Resume automation |
| GET | `/api/emergency/status` | Get pause status |
| GET | `/api/level5/eligibility` | Check Level 5 eligibility |
| POST | `/api/level5/upgrade` | Upgrade to Level 5 |

---

### 6. Dashboard Frontend

#### 6.1 New Pages

| Page | File | Purpose |
|------|------|---------|
| Policies | `app/office/policies/page.tsx` | List, create, manage policies |
| Policy Editor | `app/office/policies/[id]/page.tsx` | Visual policy builder |
| Templates | `app/office/templates/page.tsx` | Manage response templates |
| VIP Contacts | `app/office/vips/page.tsx` | Manage VIP list |
| Automation | `app/office/automation/page.tsx` | Overview, stats, emergency controls |

---

#### 6.2 New Components

| Component | File | Purpose |
|-----------|------|---------|
| PolicyCard | `components/policy-card.tsx` | Display policy with toggle |
| PolicyBuilder | `components/policy-builder.tsx` | Visual condition/action builder |
| ConditionRow | `components/condition-row.tsx` | Single condition editor |
| ActionRow | `components/action-row.tsx` | Single action editor |
| TemplateEditor | `components/template-editor.tsx` | Template with live preview |
| VIPCard | `components/vip-card.tsx` | VIP contact display |
| EmergencyButton | `components/emergency-button.tsx` | Big red pause button |
| AutomationStats | `components/automation-stats.tsx` | Execution statistics |
| PolicyExecutionLog | `components/policy-execution-log.tsx` | Recent policy fires |
| EligibilityChecker | `components/eligibility-checker.tsx` | Level 5 unlock progress |

---

#### 6.3 Emergency Button Design

The emergency pause button should be:
- **Always visible** in Level 5 mode (floating or in header)
- **Large and red** — impossible to miss
- **One-click** — no confirmation dialog (speed over safety here)
- **Keyboard accessible** — `Ctrl+Shift+P`
- **Mobile friendly** — large touch target

```tsx
// Floating emergency button (bottom-right)
<EmergencyButton
  isPaused={isPaused}
  onPause={handlePause}
  onResume={handleResume}
  className="fixed bottom-6 right-6 z-50"
/>
```

---

### 7. Configuration Updates

**File:** `args/office_integration.yaml`

Add Level 5 settings:

```yaml
level_5:
  # Progressive trust requirements
  progressive_trust:
    required_days_at_level_4: 90
    max_undo_rate: 0.05  # 5%
    min_actions_executed: 50

  # Policy limits
  policy_limits:
    max_policies_per_account: 50
    max_conditions_per_policy: 10
    max_actions_per_policy: 5
    max_executions_per_day_per_policy: 100

  # Automation settings
  automation:
    inbox_poll_interval_seconds: 60
    calendar_poll_interval_seconds: 300
    batch_size: 50

  # Safety settings
  safety:
    novel_situation_threshold: 0.7  # Confidence below this = prompt user
    require_undo_window: true       # Even autonomous actions get undo window
    vip_always_notify: true         # VIPs bypass notification suppression
    emergency_pause_default_hours: null  # Until manual resume

  # Default policy settings
  default_policies:
    auto_enable: false              # User must enable each policy
    show_suggestions: true          # Suggest policies based on behavior

  # Response templates
  templates:
    max_templates: 20
    max_template_length: 5000       # Characters
```

---

### 8. ADHD-Specific Features

| Feature | Implementation |
|---------|----------------|
| **Set and Forget** | Policies run automatically, no daily maintenance |
| **Protected Focus** | Calendar guardian declines meetings during focus time |
| **VIP Override** | Important people always get through |
| **One-Click Stop** | Emergency pause for overwhelm moments |
| **No Guilt** | Failed policies don't accumulate guilt messages |
| **Novel Handling** | Unknown situations prompt user instead of guessing |
| **Daily Summary** | Clear, brief recap of what Dex did |
| **Gradual Unlock** | 90-day trust building prevents premature automation |

---

## Implementation Order

| Step | Description | Files |
|------|-------------|-------|
| 1 | Policy data models | `tools/office/policies/__init__.py` |
| 2 | Condition matcher | `tools/office/policies/matcher.py` |
| 3 | Policy engine | `tools/office/policies/engine.py` |
| 4 | Policy manager | `tools/office/policies/manager.py` |
| 5 | Default policies | `tools/office/policies/defaults.py` |
| 6 | Emergency pause system | `tools/office/automation/emergency.py` |
| 7 | VIP contact manager | `tools/office/automation/contact_manager.py` |
| 8 | Inbox processor | `tools/office/automation/inbox_processor.py` |
| 9 | Calendar guardian | `tools/office/automation/calendar_guardian.py` |
| 10 | Auto-responder | `tools/office/automation/auto_responder.py` |
| 11 | Backend routes | `tools/dashboard/backend/routes/policies.py` |
| 12 | Frontend: Automation overview | `app/office/automation/page.tsx` |
| 13 | Frontend: Policy management | `app/office/policies/page.tsx` |
| 14 | Frontend: Policy builder | `components/policy-builder.tsx` |
| 15 | Frontend: Emergency button | `components/emergency-button.tsx` |
| 16 | Frontend: VIP management | `app/office/vips/page.tsx` |
| 17 | Frontend: Templates | `app/office/templates/page.tsx` |
| 18 | Level 5 upgrade flow | Dashboard + backend |
| 19 | Background workers | Inbox watcher, calendar watcher |
| 20 | Integration tests | `tests/integration/test_office_level5.py` |

---

## Verification Checklist

### Policy System
- [ ] `office_policies` table working
- [ ] `office_policy_executions` table logs fires
- [ ] Policy engine evaluates conditions correctly
- [ ] Actions execute via action queue
- [ ] Priority ordering respected
- [ ] Rate limits enforced per policy

### Default Policies
- [ ] Newsletter archiver works
- [ ] VIP notify works
- [ ] Focus time protection works
- [ ] Team meeting auto-accept works
- [ ] Vacation auto-reply works (when enabled)

### Emergency System
- [ ] Emergency pause stops all automation
- [ ] Resume restores automation
- [ ] Pause status shown in dashboard
- [ ] Emergency button always visible in Level 5
- [ ] Channel command `!pause` works
- [ ] Keyboard shortcut works

### VIP System
- [ ] VIPs can be added/removed
- [ ] VIP emails bypass normal policies
- [ ] VIP always notifies (ignores flow state)
- [ ] Suggestions based on email history

### Templates
- [ ] Templates can be created/edited
- [ ] Variable substitution works
- [ ] Preview shows rendered output
- [ ] Auto-reply uses templates

### Level 5 Upgrade
- [ ] Eligibility check works (90 days, <5% undo, 50+ actions)
- [ ] Acknowledgment flow required
- [ ] Default policies imported (disabled)
- [ ] Emergency button appears after upgrade

### Background Workers
- [ ] Inbox watcher processes new emails
- [ ] Calendar watcher processes meeting requests
- [ ] Workers respect emergency pause
- [ ] Workers handle errors gracefully

### Dashboard
- [ ] Policies page lists all policies
- [ ] Policy builder creates valid policies
- [ ] Automation page shows stats
- [ ] Emergency button works
- [ ] VIP page manages contacts
- [ ] Templates page manages templates

---

## Security Considerations

### Policy Validation
- All policies validated before save
- Conditions checked for valid fields/operators
- Actions checked for valid types/parameters
- Malformed policies rejected

### Rate Limiting
- Per-policy execution limits
- Per-account daily limits
- Cooldown periods between executions
- Emergency rate limit: 1000 actions/hour max

### Audit Trail
- Every policy execution logged
- Includes trigger, conditions matched, actions taken
- Cannot be deleted or modified
- Exported for compliance

### Emergency Access
- Pause works even if dashboard fails
- API endpoint requires authentication only (no other checks)
- Channel command works independently
- Automatic pause on repeated failures

---

## Reference Files

| Purpose | File |
|---------|------|
| Database schema | `tools/office/__init__.py:144-158` |
| IntegrationLevel enum | `tools/office/models.py:20-36` |
| Action queue | `tools/office/actions/queue.py` |
| Audit logger | `tools/office/actions/audit_logger.py` |
| Notification system | `tools/automation/notify.py` |
| Flow detection | `tools/automation/flow_detector.py` |

---

*Last updated: 2026-02-03*
