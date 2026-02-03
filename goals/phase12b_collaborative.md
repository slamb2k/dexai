# Phase 12b: Collaborative Office Integration (Level 3)

> **Status:** Implementation Complete
> **Prerequisites:** Phase 12a (Foundation) ✅
> **Scope:** Draft management, meeting scheduling, ADHD-safe confirmations

---

## Executive Summary

Phase 12b builds on Phase 12a's foundation to enable **Level 3 (Collaborative)** functionality. This level allows DexAI to create email drafts and schedule meetings on behalf of users, while maintaining ADHD-friendly safeguards that require user review before any external action.

**Key Principle:** Dex proposes, user disposes. Nothing leaves the user's identity without explicit confirmation.

---

## Current State (Phase 12a Complete)

### Already Implemented at Provider Level

| Provider | Method | Status |
|----------|--------|--------|
| Google | `create_draft()` | ✅ Implemented |
| Google | `get_drafts()` | ✅ Implemented |
| Google | `delete_draft()` | ✅ Implemented |
| Google | `create_event()` | ✅ Implemented |
| Google | `update_event()` | ✅ Implemented |
| Microsoft | `create_draft()` | ✅ Implemented |
| Microsoft | `get_drafts()` | ✅ Implemented |
| Microsoft | `delete_draft()` | ✅ Implemented |
| Microsoft | `create_event()` | ✅ Implemented |
| Microsoft | `update_event()` | ✅ Implemented |

### OAuth Scopes (Already Configured)

- **Google:** `gmail.modify`, `calendar` (full read/write)
- **Microsoft:** `Mail.ReadWrite`, `Calendars.ReadWrite`

---

## Implementation Plan

### 1. Database Schema Updates

**File:** `tools/office/__init__.py`

Add to `get_connection()` function:

```sql
-- Local draft tracking (tracks Dex-created drafts)
CREATE TABLE IF NOT EXISTS office_drafts (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    provider_draft_id TEXT,
    subject TEXT,
    recipients TEXT,                      -- JSON array
    cc TEXT,                              -- JSON array
    bcc TEXT,                             -- JSON array
    body_text TEXT,
    body_html TEXT,
    reply_to_message_id TEXT,
    status TEXT DEFAULT 'pending',        -- pending, approved, sent, deleted
    created_by TEXT DEFAULT 'dex',
    sentiment_score REAL,
    sentiment_flags TEXT,                 -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- Meeting proposals (tracks Dex-proposed meetings)
CREATE TABLE IF NOT EXISTS office_meeting_drafts (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    provider_event_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    attendees TEXT,                       -- JSON array
    organizer_email TEXT,
    status TEXT DEFAULT 'proposed',       -- proposed, confirmed, cancelled
    created_by TEXT DEFAULT 'dex',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    confirmed_at DATETIME,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_drafts_account_status
    ON office_drafts(account_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_created
    ON office_drafts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meeting_drafts_account_status
    ON office_meeting_drafts(account_id, status);
CREATE INDEX IF NOT EXISTS idx_meeting_drafts_start
    ON office_meeting_drafts(start_time);
```

---

### 2. Unified Tools Layer

#### 2.1 Draft Manager Tool

**File:** `tools/office/email/draft_manager.py`

**Purpose:** High-level interface for draft management with ADHD features.

**Functions:**

```python
async def create_draft(
    account_id: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    check_sentiment: bool = True,
) -> dict[str, Any]
# Returns: {"success": True, "draft_id": str, "provider_draft_id": str, "sentiment_analysis": dict}

async def get_pending_drafts(account_id: str, limit: int = 20) -> dict[str, Any]
# Returns: {"success": True, "drafts": list, "total": int}

async def approve_draft(draft_id: str, send_immediately: bool = False) -> dict[str, Any]
# Returns: {"success": True, "status": "approved"|"sent"}

async def update_draft(draft_id: str, **updates) -> dict[str, Any]

async def delete_draft(draft_id: str) -> dict[str, Any]

async def get_draft(draft_id: str) -> dict[str, Any]
```

**CLI Interface:**
```bash
python tools/office/email/draft_manager.py --account-id <id> --create --to "user@example.com" --subject "Test" --body "Hello"
python tools/office/email/draft_manager.py --account-id <id> --list-pending
python tools/office/email/draft_manager.py --account-id <id> --approve <draft-id>
python tools/office/email/draft_manager.py --account-id <id> --delete <draft-id>
```

---

#### 2.2 Meeting Scheduler Tool

**File:** `tools/office/calendar/scheduler.py`

**Purpose:** High-level interface for meeting scheduling with availability checking.

**Functions:**

```python
async def propose_meeting(
    account_id: str,
    title: str,
    start_time: datetime,
    end_time: datetime,
    attendees: list[str] | None = None,
    description: str = "",
    location: str = "",
    check_availability: bool = True,
) -> dict[str, Any]
# Returns: {"success": True, "proposal_id": str, "conflicts": list}

async def get_pending_proposals(account_id: str, limit: int = 20) -> dict[str, Any]

async def confirm_meeting(proposal_id: str) -> dict[str, Any]
# Creates actual calendar event and sends invites

async def cancel_proposal(proposal_id: str) -> dict[str, Any]

async def suggest_meeting_times(
    account_id: str,
    duration_minutes: int = 30,
    attendee_emails: list[str] | None = None,
    days_ahead: int = 7,
) -> dict[str, Any]
# Returns: {"success": True, "suggestions": list[{"start": str, "end": str, "score": float}]}
```

**CLI Interface:**
```bash
python tools/office/calendar/scheduler.py --account-id <id> --propose --title "Meeting" --start "2026-02-04T10:00:00" --duration 30
python tools/office/calendar/scheduler.py --account-id <id> --list-pending
python tools/office/calendar/scheduler.py --account-id <id> --confirm <proposal-id>
python tools/office/calendar/scheduler.py --account-id <id> --suggest --duration 30 --days 7
```

---

#### 2.3 Sentiment Analysis

**File:** `tools/office/email/sentiment.py`

**Purpose:** Basic sentiment detection for outgoing emails.

```python
def analyze_email_sentiment(subject: str, body: str) -> dict[str, Any]:
    """
    Analyze email for emotional content that ADHD users might regret sending.

    Returns:
        {
            "score": float,           # 0.0 (calm) to 1.0 (highly emotional)
            "flags": list[str],       # ["negative_tone", "strong_language", etc.]
            "suggestion": str | None, # "Consider waiting before sending"
            "safe_to_send": bool
        }
    """
```

**Detection patterns:**
- Negative language (similar to RSD detection in `tools/adhd/language_filter.py`)
- Strong emotional words ("furious", "disappointed", "unacceptable")
- ALL CAPS sections
- Excessive punctuation (!!!, ???)
- Reactive phrasing ("in response to your...", "I can't believe...")

---

### 3. Dashboard Backend Routes

#### 3.1 Office Routes

**File:** `tools/dashboard/backend/routes/office.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/office/accounts` | List connected accounts |
| GET | `/api/office/accounts/{id}` | Get account details |
| PUT | `/api/office/accounts/{id}/level` | Change integration level |
| GET | `/api/office/drafts` | List drafts (with filters) |
| GET | `/api/office/drafts/{id}` | Get draft details |
| POST | `/api/office/drafts` | Create new draft |
| PUT | `/api/office/drafts/{id}` | Update draft |
| DELETE | `/api/office/drafts/{id}` | Delete draft |
| POST | `/api/office/drafts/{id}/approve` | Approve draft |
| GET | `/api/office/meetings` | List meeting proposals |
| GET | `/api/office/meetings/{id}` | Get meeting details |
| POST | `/api/office/meetings` | Propose new meeting |
| PUT | `/api/office/meetings/{id}` | Update proposal |
| DELETE | `/api/office/meetings/{id}` | Cancel proposal |
| POST | `/api/office/meetings/{id}/confirm` | Confirm meeting |
| GET | `/api/office/availability` | Check availability |
| GET | `/api/office/suggest-times` | Get meeting time suggestions |

---

#### 3.2 OAuth Callback Routes

**File:** `tools/dashboard/backend/routes/oauth.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/oauth/google/callback` | Google OAuth callback |
| GET | `/oauth/microsoft/callback` | Microsoft OAuth callback |
| GET | `/oauth/status` | Check OAuth status |
| POST | `/oauth/revoke` | Revoke OAuth tokens |

---

#### 3.3 Pydantic Models

**File:** `tools/dashboard/backend/models.py` (additions)

```python
class DraftCreateRequest(BaseModel):
    account_id: str
    to: list[str]
    subject: str
    body: str
    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to_message_id: str | None = None

class DraftResponse(BaseModel):
    id: str
    account_id: str
    provider_draft_id: str | None
    subject: str
    recipients: list[str]
    body_preview: str
    status: str
    sentiment_score: float | None
    sentiment_flags: list[str]
    created_at: str

class MeetingProposalRequest(BaseModel):
    account_id: str
    title: str
    start_time: str  # ISO format
    end_time: str
    attendees: list[str] | None = None
    description: str = ""
    location: str = ""

class MeetingProposalResponse(BaseModel):
    id: str
    account_id: str
    provider_event_id: str | None
    title: str
    start_time: str
    end_time: str
    attendees: list[str]
    status: str
    conflicts: list[dict] | None
    created_at: str
```

---

### 4. Dashboard Frontend

#### 4.1 New Pages

| Page | File | Purpose |
|------|------|---------|
| Office Hub | `app/office/page.tsx` | Connected accounts, integration level, quick stats |
| Drafts | `app/office/drafts/page.tsx` | List pending drafts, approve/edit/delete |
| Meetings | `app/office/meetings/page.tsx` | List proposals, confirm/cancel, suggest times |

---

#### 4.2 New Components

| Component | File | Purpose |
|-----------|------|---------|
| DraftCard | `components/draft-card.tsx` | Display draft with actions |
| MeetingCard | `components/meeting-card.tsx` | Display meeting proposal |
| SentimentBadge | `components/sentiment-badge.tsx` | Show sentiment warnings |
| TimeSlotPicker | `components/time-slot-picker.tsx` | Select meeting times |
| AttendeeList | `components/attendee-list.tsx` | Show/edit attendees |
| ConflictWarning | `components/conflict-warning.tsx` | Display calendar conflicts |

---

#### 4.3 API Client Updates

**File:** `tools/dashboard/frontend/lib/api.ts`

Add TypeScript types and methods for:
- `OfficeDraft` interface
- `MeetingProposal` interface
- `TimeSuggestion` interface
- CRUD methods for drafts and meetings

---

### 5. ADHD-Specific Features

| Feature | Implementation |
|---------|----------------|
| **Sentiment Analysis** | Flag emotional emails before sending |
| **Draft Preview** | Show full content before save, require confirmation |
| **Meeting Confirmation** | List all attendees, show what notification they receive |
| **Buffer Time** | Suggest transition time between meetings |
| **No Auto-Send** | Level 3 never sends automatically (Level 4+ feature) |

---

## Implementation Order

| Step | Description | Files |
|------|-------------|-------|
| 1 | Database schema | `tools/office/__init__.py` |
| 2 | Draft manager tool | `tools/office/email/draft_manager.py` |
| 3 | Meeting scheduler tool | `tools/office/calendar/scheduler.py` |
| 4 | Sentiment analysis | `tools/office/email/sentiment.py` |
| 5 | Backend routes | `tools/dashboard/backend/routes/office.py`, `oauth.py` |
| 6 | Frontend - Office hub | `app/office/page.tsx` |
| 7 | Frontend - Drafts | `app/office/drafts/page.tsx`, components |
| 8 | Frontend - Meetings | `app/office/meetings/page.tsx`, components |
| 9 | Integration testing | `tests/integration/test_office_level3.py` |

---

## Verification Checklist

### Tools Layer
- [ ] `office_drafts` and `office_meeting_drafts` tables created
- [ ] `draft_manager.py` exists with CLI interface
- [ ] `scheduler.py` exists with CLI interface
- [ ] `sentiment.py` provides basic detection
- [ ] Draft creation checks Level 3+ requirement
- [ ] Meeting creation checks Level 3+ requirement

### Dashboard Backend
- [ ] `/api/office/drafts` endpoints work
- [ ] `/api/office/meetings` endpoints work
- [ ] `/api/office/availability` returns correct data
- [ ] `/oauth/google/callback` handles OAuth flow
- [ ] `/oauth/microsoft/callback` handles OAuth flow

### Dashboard Frontend
- [ ] `/office` page shows connected accounts
- [ ] `/office/drafts` shows pending drafts
- [ ] `/office/meetings` shows meeting proposals
- [ ] Draft approval flow works end-to-end
- [ ] Meeting confirmation flow works end-to-end
- [ ] Sentiment warnings display correctly

### ADHD Features
- [ ] Sentiment analysis flags emotional emails
- [ ] Draft preview shows full content before save
- [ ] Meeting confirmation lists all attendees
- [ ] No actions happen without explicit user confirmation

### Integration
- [ ] Google draft appears in Gmail Drafts folder
- [ ] Microsoft draft appears in Outlook Drafts folder
- [ ] Google calendar event created on confirm
- [ ] Microsoft calendar event created on confirm
- [ ] Attendees receive invites from user's address

---

## Reference Files

| Purpose | File |
|---------|------|
| Provider patterns | `tools/office/providers/google_workspace.py:437-495` |
| Event patterns | `tools/office/providers/google_workspace.py:556-625` |
| Route patterns | `tools/dashboard/backend/routes/setup.py` |
| Frontend patterns | `tools/dashboard/frontend/app/settings/page.tsx` |
| Sentiment patterns | `tools/adhd/language_filter.py` |

---

*Last updated: 2026-02-03*
