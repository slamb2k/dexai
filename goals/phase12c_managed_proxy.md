# Phase 12c: Managed Proxy Office Integration (Level 4)

> **Status:** Planned
> **Prerequisites:** Phase 12b (Collaborative) complete
> **Scope:** Send with undo, delete with confirmation, full audit trail, daily digest

---

## Executive Summary

Phase 12c builds on Phase 12b's collaborative features to enable **Level 4 (Managed Proxy)** functionality. This level allows DexAI to send emails and manage calendar events on behalf of users, with ADHD-specific safeguards including extended undo windows, sentiment-gated sending, and comprehensive audit trails.

**Key Principle:** Every action can be undone. Nothing is permanent until the undo window closes.

---

## Current State (Phase 12b Complete)

### Already Implemented

| Component | Status |
|-----------|--------|
| Database: `office_actions` table | Ready (schema exists) |
| Database: `office_audit_log` table | Ready (schema exists) |
| Model: `OfficeAction` dataclass | Ready in `models.py` |
| Model: `IntegrationLevel.MANAGED_PROXY` | Ready |
| Method: `OfficeAccount.can_send_email()` | Ready |
| Provider: `google_workspace.send_email()` | Needs implementation |
| Provider: `microsoft_365.send_email()` | Needs implementation |
| Sentiment analysis | Ready in `email/sentiment.py` |

### OAuth Scopes (Already Configured in `args/office_integration.yaml`)

- **Google Level 4:** `gmail.modify`, `gmail.send`, `calendar`
- **Microsoft Level 4:** `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Request                             │
│         "Send this email" / "Delete that message"           │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Action Queue                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ queue.py    │  │ validator.py│  │ undo_mgr.py │         │
│  │ Queue action│→ │ Check level │→ │ Set deadline│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Undo Window (60s)                         │
│  User can: Cancel / Modify / Approve immediately            │
└─────────────────────────┬───────────────────────────────────┘
                          ▼ (if not undone)
┌─────────────────────────────────────────────────────────────┐
│                    Action Executor                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ executor.py │→ │ Provider    │→ │ audit_log.py│         │
│  │ Run action  │  │ API call    │  │ Log result  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### 1. Directory Structure

```
tools/office/actions/
├── __init__.py                    # Path constants, action types
├── queue.py                       # Action queue management
├── validator.py                   # Pre-execution validation
├── executor.py                    # Execute queued actions
├── undo_manager.py                # Undo window management
├── audit_logger.py                # Permanent action logging
└── digest.py                      # Daily digest generation

tools/office/email/
└── sender.py                      # Send emails (Level 4+)

tools/dashboard/backend/routes/
└── actions.py                     # Action queue API endpoints
```

---

### 2. Database Schema Additions

**File:** `tools/office/__init__.py`

Add indexes for action queue performance:

```sql
-- Additional indexes for Level 4
CREATE INDEX IF NOT EXISTS idx_actions_account_status
    ON office_actions(account_id, status);
CREATE INDEX IF NOT EXISTS idx_actions_deadline
    ON office_actions(undo_deadline)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_audit_type_date
    ON office_audit_log(action_type, created_at);
```

---

### 3. Action Queue System

#### 3.1 Action Queue Manager

**File:** `tools/office/actions/queue.py`

**Purpose:** Queue actions with undo deadlines, manage pending actions.

**Functions:**

```python
async def queue_action(
    account_id: str,
    action_type: str,
    action_data: dict[str, Any],
    undo_window_seconds: int = 60,
    priority: str = "normal",  # "normal", "high", "low"
    require_confirmation: bool = False,
) -> dict[str, Any]
# Returns: {"success": True, "action_id": str, "undo_deadline": str, "status": "pending"}

async def get_pending_actions(
    account_id: str,
    action_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]
# Returns: {"success": True, "actions": list[OfficeAction], "total": int}

async def get_action(action_id: str) -> dict[str, Any]
# Returns: {"success": True, "action": OfficeAction}

async def cancel_action(action_id: str, reason: str = "") -> dict[str, Any]
# Returns: {"success": True, "status": "cancelled"}

async def expedite_action(action_id: str) -> dict[str, Any]
# Execute immediately, skip undo window
# Returns: {"success": True, "status": "executed"}

async def get_queue_stats(account_id: str) -> dict[str, Any]
# Returns: {"pending": int, "executed_today": int, "undone_today": int}
```

**CLI Interface:**
```bash
python tools/office/actions/queue.py --account-id <id> --list-pending
python tools/office/actions/queue.py --account-id <id> --cancel <action-id>
python tools/office/actions/queue.py --account-id <id> --expedite <action-id>
python tools/office/actions/queue.py --account-id <id> --stats
```

---

#### 3.2 Action Validator

**File:** `tools/office/actions/validator.py`

**Purpose:** Validate actions before queuing (level check, rate limits, content).

**Functions:**

```python
def validate_action(
    account: OfficeAccount,
    action_type: str,
    action_data: dict[str, Any],
) -> dict[str, Any]
# Returns: {"valid": bool, "errors": list[str], "warnings": list[str]}

def check_rate_limits(account_id: str, action_type: str) -> dict[str, Any]
# Returns: {"allowed": bool, "remaining": int, "reset_at": str}

def check_recipient_safety(recipients: list[str]) -> dict[str, Any]
# Warn about external domains, large recipient lists
# Returns: {"safe": bool, "warnings": list[str]}
```

**Validation Rules:**
- Account must be Level 4+
- Action type must be valid
- Rate limits not exceeded (configurable per action type)
- Recipients validated (warn on external domains)
- Content passes sentiment check for emails

---

#### 3.3 Undo Manager

**File:** `tools/office/actions/undo_manager.py`

**Purpose:** Manage undo windows, handle undo requests.

**Functions:**

```python
async def undo_action(action_id: str) -> dict[str, Any]
# Returns: {"success": True, "status": "undone"} or {"success": False, "error": "..."}

async def extend_undo_window(action_id: str, additional_seconds: int = 30) -> dict[str, Any]
# Returns: {"success": True, "new_deadline": str}

async def get_undoable_actions(account_id: str) -> dict[str, Any]
# Returns actions still within undo window
# Returns: {"success": True, "actions": list, "count": int}

def calculate_undo_deadline(
    action_type: str,
    sentiment_score: float | None = None,
) -> datetime
# Returns appropriate deadline based on action type and sentiment
# High sentiment = longer window (up to 5 minutes)
```

**Undo Window Configuration:**
```yaml
undo_windows:
  send_email:
    default: 60
    high_sentiment: 300  # 5 minutes for emotional emails
  delete_email: 30
  archive_email: 15
  schedule_meeting: 60
  cancel_meeting: 60
```

---

#### 3.4 Action Executor

**File:** `tools/office/actions/executor.py`

**Purpose:** Execute actions after undo window expires.

**Functions:**

```python
async def execute_action(action_id: str) -> dict[str, Any]
# Returns: {"success": True, "result": dict} or {"success": False, "error": str}

async def process_expired_actions() -> dict[str, Any]
# Background task: find and execute all expired pending actions
# Returns: {"processed": int, "succeeded": int, "failed": int}

async def retry_failed_action(action_id: str) -> dict[str, Any]
# Retry a failed action
# Returns: {"success": True, "result": dict}
```

**Execution Flow:**
1. Check action still pending (not undone)
2. Check undo deadline has passed
3. Get provider for account
4. Execute via provider API
5. Log to audit trail
6. Update action status

**Background Worker:**
```python
# Run every 5 seconds to process expired actions
async def action_worker():
    while True:
        await process_expired_actions()
        await asyncio.sleep(5)
```

---

#### 3.5 Audit Logger

**File:** `tools/office/actions/audit_logger.py`

**Purpose:** Permanent, immutable log of all actions.

**Functions:**

```python
async def log_action(
    account_id: str,
    action_type: str,
    action_summary: str,
    action_data: dict[str, Any],
    result: str,  # "success", "failed", "undone"
    related_action_id: str | None = None,
) -> dict[str, Any]
# Returns: {"success": True, "log_id": str}

async def get_audit_log(
    account_id: str,
    action_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    result: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]
# Returns: {"success": True, "entries": list, "total": int}

async def export_audit_log(
    account_id: str,
    format: str = "csv",  # "csv", "json"
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]
# Returns: {"success": True, "file_path": str, "entries": int}

async def get_audit_summary(
    account_id: str,
    period: str = "day",  # "day", "week", "month"
) -> dict[str, Any]
# Returns: {"success": True, "summary": dict}
```

**Audit Entry Fields:**
- `id`: Unique log entry ID
- `account_id`: Account that performed action
- `action_type`: Type of action
- `action_summary`: Human-readable summary ("Sent email to john@example.com: 'Meeting follow-up'")
- `action_data`: Full action data (may be redacted for privacy)
- `result`: "success", "failed", "undone"
- `created_at`: Timestamp

**CLI Interface:**
```bash
python tools/office/actions/audit_logger.py --account-id <id> --list --limit 50
python tools/office/actions/audit_logger.py --account-id <id> --export csv --output audit.csv
python tools/office/actions/audit_logger.py --account-id <id> --summary week
```

---

#### 3.6 Daily Digest Generator

**File:** `tools/office/actions/digest.py`

**Purpose:** Generate daily summary of all Dex actions.

**Functions:**

```python
async def generate_digest(
    account_id: str,
    date: datetime | None = None,  # Default: yesterday
) -> dict[str, Any]
# Returns: {"success": True, "digest": DigestContent}

async def send_digest(
    account_id: str,
    channel: str = "primary",  # Notification channel
) -> dict[str, Any]
# Returns: {"success": True, "sent_via": str}

async def schedule_digest(
    account_id: str,
    send_time: str = "20:00",
    timezone: str = "UTC",
) -> dict[str, Any]
# Returns: {"success": True, "scheduled_for": str}
```

**Digest Content:**
```python
@dataclass
class DigestContent:
    date: datetime
    emails_sent: int
    emails_deleted: int
    meetings_scheduled: int
    meetings_cancelled: int
    actions_undone: int
    highlights: list[str]  # Notable actions
    warnings: list[str]    # Any issues
```

**Digest Format (ADHD-friendly):**
```
Daily Dex Summary - Feb 3, 2026

Today I helped you with:
  - Sent 3 emails
  - Scheduled 1 meeting
  - Archived 12 newsletters

You undid 1 action (good catch!)

No issues to report.
```

---

### 4. Email Sender

**File:** `tools/office/email/sender.py`

**Purpose:** Send emails through the action queue system.

**Functions:**

```python
async def send_email(
    account_id: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    attachments: list[dict] | None = None,
    skip_sentiment_check: bool = False,
) -> dict[str, Any]
# Queues email for sending with undo window
# Returns: {"success": True, "action_id": str, "undo_deadline": str}

async def send_draft(
    draft_id: str,
    skip_undo: bool = False,
) -> dict[str, Any]
# Convert draft to send action
# Returns: {"success": True, "action_id": str}

async def delete_email(
    account_id: str,
    message_id: str,
    permanent: bool = False,
) -> dict[str, Any]
# Queue deletion (trash by default, permanent requires confirmation)
# Returns: {"success": True, "action_id": str}

async def archive_email(
    account_id: str,
    message_id: str,
) -> dict[str, Any]
# Returns: {"success": True, "action_id": str}

async def bulk_action(
    account_id: str,
    message_ids: list[str],
    action: str,  # "archive", "delete", "mark_read"
) -> dict[str, Any]
# Returns: {"success": True, "action_id": str, "count": int}
```

**CLI Interface:**
```bash
python tools/office/email/sender.py --account-id <id> --send --to "user@example.com" --subject "Test" --body "Hello"
python tools/office/email/sender.py --account-id <id> --send-draft <draft-id>
python tools/office/email/sender.py --account-id <id> --delete <message-id>
python tools/office/email/sender.py --account-id <id> --archive <message-id>
```

---

### 5. Provider Updates

#### 5.1 Google Workspace Additions

**File:** `tools/office/providers/google_workspace.py`

Add methods:

```python
async def send_email(
    self,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    attachments: list[dict] | None = None,
) -> dict[str, Any]
# Uses Gmail API messages.send()

async def trash_email(self, message_id: str) -> dict[str, Any]
# Uses Gmail API messages.trash()

async def delete_email(self, message_id: str) -> dict[str, Any]
# Uses Gmail API messages.delete() - permanent

async def archive_email(self, message_id: str) -> dict[str, Any]
# Removes INBOX label

async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]
# Uses Calendar API events.delete()
```

---

#### 5.2 Microsoft 365 Additions

**File:** `tools/office/providers/microsoft_365.py`

Add methods:

```python
async def send_email(
    self,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    attachments: list[dict] | None = None,
) -> dict[str, Any]
# Uses Graph API /me/sendMail

async def move_to_deleted(self, message_id: str) -> dict[str, Any]
# Uses Graph API move to deletedItems

async def delete_email(self, message_id: str) -> dict[str, Any]
# Uses Graph API DELETE - permanent

async def archive_email(self, message_id: str) -> dict[str, Any]
# Uses Graph API move to archive

async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]
# Uses Graph API DELETE /me/events/{id}
```

---

### 6. Dashboard Backend Routes

**File:** `tools/dashboard/backend/routes/actions.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/actions` | List pending actions (with filters) |
| GET | `/api/actions/{id}` | Get action details |
| POST | `/api/actions/{id}/undo` | Undo pending action |
| POST | `/api/actions/{id}/expedite` | Execute immediately |
| POST | `/api/actions/{id}/extend` | Extend undo window |
| GET | `/api/audit` | Get audit log (with filters) |
| GET | `/api/audit/export` | Export audit log |
| GET | `/api/audit/summary` | Get period summary |
| POST | `/api/email/send` | Queue email send |
| POST | `/api/email/{id}/delete` | Queue email delete |
| POST | `/api/email/{id}/archive` | Queue email archive |
| POST | `/api/email/bulk` | Bulk email actions |
| GET | `/api/digest/preview` | Preview today's digest |
| POST | `/api/digest/send` | Send digest now |

---

### 7. Dashboard Frontend

#### 7.1 New Pages

| Page | File | Purpose |
|------|------|---------|
| Action Queue | `app/office/actions/page.tsx` | View pending actions, undo, expedite |
| Audit Log | `app/office/audit/page.tsx` | Browse action history, export |

---

#### 7.2 New Components

| Component | File | Purpose |
|-----------|------|---------|
| ActionCard | `components/action-card.tsx` | Display pending action with countdown |
| UndoButton | `components/undo-button.tsx` | Prominent undo with countdown timer |
| ActionTimeline | `components/action-timeline.tsx` | Visual timeline of actions |
| AuditTable | `components/audit-table.tsx` | Sortable, filterable audit log |
| DigestPreview | `components/digest-preview.tsx` | Preview daily digest |
| CountdownTimer | `components/countdown-timer.tsx` | Visual undo countdown |

---

#### 7.3 Real-time Updates

**WebSocket Events:**
```typescript
// Action queued
{ type: "action_queued", action_id: string, action_type: string, undo_deadline: string }

// Action executed
{ type: "action_executed", action_id: string, result: "success" | "failed" }

// Action undone
{ type: "action_undone", action_id: string }

// Undo window closing soon (10s warning)
{ type: "undo_warning", action_id: string, seconds_remaining: number }
```

---

### 8. Configuration Updates

**File:** `args/office_integration.yaml`

Add Level 4 settings:

```yaml
level_4:
  # Undo window defaults (seconds)
  undo_windows:
    send_email: 60
    send_email_high_sentiment: 300
    delete_email: 30
    archive_email: 15
    schedule_meeting: 60
    cancel_meeting: 60

  # Rate limits (per hour)
  rate_limits:
    send_email: 50
    delete_email: 100
    archive_email: 200

  # Confirmation requirements
  require_confirmation:
    - permanent_delete
    - send_to_large_group  # >10 recipients
    - external_domain_first_contact

  # Daily digest
  digest:
    enabled: true
    send_time: "20:00"
    timezone: "user"  # Use user's timezone
    channel: "primary"

  # Audit settings
  audit:
    retention_days: 365
    include_body_preview: true
    redact_after_days: 90  # Redact full content after 90 days
```

---

### 9. ADHD-Specific Features

| Feature | Implementation |
|---------|----------------|
| **Extended Undo** | 60s default, 5 min for emotional emails |
| **Visual Countdown** | Prominent timer showing undo window |
| **Sentiment Gating** | High-sentiment emails get longer window + warning |
| **Daily Digest** | Non-judgmental summary of actions |
| **One-Click Undo** | Undo button on all notifications |
| **Bulk Undo** | "Undo all pending" for overwhelm moments |
| **Confirmation Dialogs** | Clear, non-scary language for destructive actions |

---

## Implementation Order

| Step | Description | Files |
|------|-------------|-------|
| 1 | Action queue core | `tools/office/actions/__init__.py`, `queue.py` |
| 2 | Validator | `tools/office/actions/validator.py` |
| 3 | Undo manager | `tools/office/actions/undo_manager.py` |
| 4 | Executor | `tools/office/actions/executor.py` |
| 5 | Audit logger | `tools/office/actions/audit_logger.py` |
| 6 | Email sender | `tools/office/email/sender.py` |
| 7 | Provider: Google send | `tools/office/providers/google_workspace.py` |
| 8 | Provider: Microsoft send | `tools/office/providers/microsoft_365.py` |
| 9 | Digest generator | `tools/office/actions/digest.py` |
| 10 | Backend routes | `tools/dashboard/backend/routes/actions.py` |
| 11 | Frontend: Actions page | `app/office/actions/page.tsx` |
| 12 | Frontend: Audit page | `app/office/audit/page.tsx` |
| 13 | WebSocket events | `tools/dashboard/backend/websocket.py` |
| 14 | Configuration | `args/office_integration.yaml` |
| 15 | Integration tests | `tests/integration/test_office_level4.py` |

---

## Verification Checklist

### Action Queue
- [ ] `tools/office/actions/__init__.py` exists with action types
- [ ] `queue.py` can queue actions with undo deadlines
- [ ] `validator.py` checks level requirements
- [ ] `undo_manager.py` can undo pending actions
- [ ] `executor.py` processes expired actions
- [ ] Background worker runs every 5 seconds
- [ ] Rate limits enforced

### Audit System
- [ ] `audit_logger.py` logs all actions
- [ ] Audit entries include summary and data
- [ ] Export to CSV works
- [ ] Export to JSON works
- [ ] Retention policy applied

### Email Operations
- [ ] `sender.py` queues emails with undo
- [ ] Sentiment check extends undo window
- [ ] Google: send email works
- [ ] Microsoft: send email works
- [ ] Delete queues with confirmation for permanent
- [ ] Archive works for both providers
- [ ] Bulk operations work

### Dashboard
- [ ] `/api/actions` returns pending actions
- [ ] `/api/actions/{id}/undo` undoes action
- [ ] `/api/audit` returns filtered log
- [ ] `/api/audit/export` generates file
- [ ] WebSocket sends real-time updates
- [ ] Countdown timer displays correctly
- [ ] Undo button works

### Daily Digest
- [ ] `digest.py` generates correct summary
- [ ] Digest sent via notification channel
- [ ] Scheduled digest fires at correct time
- [ ] Digest is ADHD-friendly (no guilt language)

### ADHD Features
- [ ] 60-second default undo window
- [ ] High-sentiment emails get 5-minute window
- [ ] Visual countdown is prominent
- [ ] "Undo all" button available
- [ ] Confirmation dialogs use safe language

---

## Security Considerations

### Rate Limiting
- Per-account rate limits prevent runaway automation
- Configurable per action type
- Soft limits warn, hard limits block

### Audit Integrity
- Audit log is append-only (no updates/deletes)
- Entries include cryptographic hash for tamper detection
- Export includes verification checksums

### Token Security
- Tokens remain encrypted in vault
- Never exposed in audit logs
- Refresh handled automatically

### Permission Checks
- Every action validates account level
- Level 4 required for all send/delete operations
- Cannot bypass via direct API calls

---

## Reference Files

| Purpose | File |
|---------|------|
| Database schema | `tools/office/__init__.py:115-142` |
| OfficeAction model | `tools/office/models.py:417-474` |
| Sentiment analysis | `tools/office/email/sentiment.py` |
| Route patterns | `tools/dashboard/backend/routes/office.py` |
| WebSocket patterns | `tools/dashboard/backend/websocket.py` |
| Notification system | `tools/automation/notify.py` |

---

*Last updated: 2026-02-03*
