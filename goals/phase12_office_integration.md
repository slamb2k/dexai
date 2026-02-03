# Phase 12: Office Integration — Tactical Implementation Guide

**Status:** ✅ Complete
**Depends on:** Phase 0 (Security), Phase 7 (Dashboard), Phase 8 (Setup Wizard)
**Last Updated:** 2026-02-03

---

## Overview

Phase 12 provides comprehensive integration with Microsoft 365 and Google Workspace ecosystems. Unlike typical integrations, DexAI supports **5 integration levels** allowing users to choose their comfort zone—from sandboxed presence to full autonomous agent.

**Key Innovation:** Users can start at Level 1 (minimal risk) and progressively unlock higher levels as trust builds. This matches ADHD users' need for gradual adoption without overwhelming options.

---

## Sub-Phases

| Sub-Phase | Focus | Status |
|-----------|-------|--------|
| **12a** | Foundation — OAuth, Level 1-2 | ✅ Complete |
| **12b** | Collaborative — Level 3 | ✅ Complete |
| **12c** | Managed Proxy — Level 4 | ✅ Complete |
| **12d** | Autonomous — Level 5 | ✅ Complete |

---

## Integration Levels Summary

| Level | Name | Read | Write | Delete | Autonomous |
|-------|------|------|-------|--------|------------|
| 1 | Sandboxed | Dex's only | Dex's only | Dex's only | ❌ |
| 2 | Read-Only | User's | ❌ | ❌ | ❌ |
| 3 | Collaborative | User's | Drafts only | ❌ | ❌ |
| 4 | Managed Proxy | User's | With undo | With confirm | ❌ |
| 5 | Autonomous | User's | Policy-based | Policy-based | ✅ |

---

## Phase 12a: Foundation

### Objective

Establish OAuth infrastructure and provide Level 1-2 functionality (read-only access).

### Directory Structure

```
tools/office/
├── __init__.py                    # Path constants, shared utilities
├── models.py                      # Data models (Email, CalendarEvent, etc.)
├── oauth_manager.py               # OAuth flows for Google + Microsoft
├── level_detector.py              # Determine current integration level
├── onboarding.py                  # Integration level selection wizard
│
├── providers/
│   ├── __init__.py
│   ├── base.py                    # Abstract provider interface
│   ├── google_workspace.py        # Gmail, Calendar, Contacts APIs
│   ├── microsoft_365.py           # Graph API (Outlook, Calendar, Teams)
│   └── standalone_imap.py         # Level 1: Dex's own mailbox (IMAP/SMTP)
│
├── email/
│   ├── __init__.py
│   ├── reader.py                  # Inbox reading, search, filtering
│   └── summarizer.py              # Inbox summary generation
│
└── calendar/
    ├── __init__.py
    └── reader.py                  # Read events, availability
```

### Database Schema

```sql
-- Office accounts (linked OAuth connections)
CREATE TABLE IF NOT EXISTS office_accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,           -- 'google', 'microsoft', 'standalone'
    integration_level INTEGER DEFAULT 1,
    email_address TEXT,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expiry DATETIME,
    scopes TEXT,                      -- JSON array of granted scopes
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Cached emails (for offline access and search)
CREATE TABLE IF NOT EXISTS office_email_cache (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    message_id TEXT NOT NULL,         -- Provider's message ID
    thread_id TEXT,
    subject TEXT,
    sender TEXT,
    recipients TEXT,                  -- JSON array
    snippet TEXT,
    received_at DATETIME,
    labels TEXT,                      -- JSON array
    is_read BOOLEAN DEFAULT FALSE,
    is_starred BOOLEAN DEFAULT FALSE,
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- Cached calendar events
CREATE TABLE IF NOT EXISTS office_calendar_cache (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    event_id TEXT NOT NULL,           -- Provider's event ID
    calendar_id TEXT,
    title TEXT,
    description TEXT,
    location TEXT,
    start_time DATETIME,
    end_time DATETIME,
    all_day BOOLEAN DEFAULT FALSE,
    recurrence TEXT,                  -- JSON recurrence rule
    attendees TEXT,                   -- JSON array
    status TEXT,                      -- 'confirmed', 'tentative', 'cancelled'
    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_email_account_date ON office_email_cache(account_id, received_at);
CREATE INDEX IF NOT EXISTS idx_calendar_account_date ON office_calendar_cache(account_id, start_time);
```

### Implementation Order

1. **Create `tools/office/__init__.py`**
   - Path constants (PROJECT_ROOT, DB_PATH, CONFIG_PATH)
   - Common database connection function
   - Shared utilities

2. **Create `tools/office/models.py`**
   - `Email` dataclass
   - `CalendarEvent` dataclass
   - `OfficeAccount` dataclass
   - `IntegrationLevel` enum

3. **Create `tools/office/providers/base.py`**
   - Abstract `OfficeProvider` class
   - Common interface for all providers:
     - `authenticate()` → bool
     - `get_emails(query, limit)` → list[Email]
     - `get_calendar_events(start, end)` → list[CalendarEvent]
     - `get_inbox_summary()` → dict

4. **Create `tools/office/providers/standalone_imap.py`** (Level 1)
   - IMAP connection for reading Dex's own mailbox
   - SMTP for sending from Dex's identity
   - No OAuth needed—uses traditional email credentials

5. **Create `tools/office/oauth_manager.py`**
   - OAuth 2.0 flows for Google and Microsoft
   - Token storage in vault (encrypted)
   - Token refresh handling
   - Scope management per level

6. **Create `tools/office/providers/google_workspace.py`** (Level 2+)
   - Gmail API client
   - Calendar API client
   - Read-only operations for Level 2

7. **Create `tools/office/providers/microsoft_365.py`** (Level 2+)
   - Microsoft Graph API client
   - Outlook mail and calendar
   - Read-only operations for Level 2

8. **Create `tools/office/email/reader.py`**
   - Unified email reading interface
   - Search and filtering
   - Thread grouping

9. **Create `tools/office/email/summarizer.py`**
   - Inbox summary generation
   - Priority detection
   - Action item extraction

10. **Create `tools/office/calendar/reader.py`**
    - Event retrieval
    - Availability checking
    - Conflict detection

11. **Create `tools/office/level_detector.py`**
    - Determine current integration level from granted scopes
    - Suggest level upgrades when appropriate

12. **Create `tools/office/onboarding.py`**
    - Integration level selection wizard
    - Clear explanations of each level
    - OAuth flow initiation

13. **Create `args/office_integration.yaml`**
    - Default integration level
    - OAuth client IDs (placeholders)
    - Provider-specific settings

### Configuration File

```yaml
# args/office_integration.yaml

office_integration:
  # Default integration level for new users
  default_level: 2

  # Supported platforms
  platforms:
    google:
      enabled: true
      display_name: "Google Workspace"
      oauth:
        # These are placeholders - real values in vault
        client_id_env: "GOOGLE_CLIENT_ID"
        client_secret_env: "GOOGLE_CLIENT_SECRET"
        redirect_uri: "http://localhost:8080/oauth/google/callback"
      scopes_by_level:
        level_2:
          - "https://www.googleapis.com/auth/gmail.readonly"
          - "https://www.googleapis.com/auth/calendar.readonly"
        level_3:
          - "https://www.googleapis.com/auth/gmail.modify"
          - "https://www.googleapis.com/auth/calendar"
        level_4:
          - "https://www.googleapis.com/auth/gmail.modify"
          - "https://www.googleapis.com/auth/gmail.send"
          - "https://www.googleapis.com/auth/calendar"
        level_5:
          - "https://www.googleapis.com/auth/gmail.modify"
          - "https://www.googleapis.com/auth/gmail.send"
          - "https://www.googleapis.com/auth/calendar"
          - "https://www.googleapis.com/auth/contacts"

    microsoft:
      enabled: true
      display_name: "Microsoft 365"
      oauth:
        client_id_env: "MICROSOFT_CLIENT_ID"
        client_secret_env: "MICROSOFT_CLIENT_SECRET"
        redirect_uri: "http://localhost:8080/oauth/microsoft/callback"
        tenant: "common"  # or specific tenant ID
      scopes_by_level:
        level_2:
          - "Mail.Read"
          - "Calendars.Read"
        level_3:
          - "Mail.ReadWrite"
          - "Calendars.ReadWrite"
        level_4:
          - "Mail.ReadWrite"
          - "Mail.Send"
          - "Calendars.ReadWrite"
        level_5:
          - "Mail.ReadWrite"
          - "Mail.Send"
          - "Calendars.ReadWrite"
          - "Contacts.ReadWrite"

    standalone:
      enabled: true
      display_name: "Standalone Email"
      description: "Use Dex's own email address (IMAP/SMTP)"
      # No OAuth - uses traditional credentials

  # Level 1: Sandboxed settings
  sandboxed:
    # Dex's own email configuration
    imap_host: ""  # Set during setup
    imap_port: 993
    smtp_host: ""  # Set during setup
    smtp_port: 587
    email_address: ""  # e.g., dex@yourdomain.com

  # Cache settings
  cache:
    email_retention_days: 30
    calendar_sync_days_ahead: 90
    sync_interval_minutes: 15

  # ADHD-specific settings
  adhd:
    # Extended undo window (seconds)
    undo_window: 60

    # Sentiment detection threshold (0-1)
    sentiment_review_threshold: 0.7

    # Cool-off period for negative replies (minutes)
    negative_reply_delay: 10

    # Daily digest settings
    daily_digest:
      enabled: true
      send_time: "20:00"  # In user's timezone
      channel: "primary"  # Send via primary notification channel

    # Progressive trust requirements
    progressive_trust:
      level_3_days: 7      # Days at Level 2 before Level 3 unlocks
      level_4_days: 30     # Days at Level 3 before Level 4 unlocks
      level_5_days: 90     # Days at Level 4 before Level 5 unlocks
```

### Verification Checklist

- [ ] `tools/office/__init__.py` exists with path constants
- [ ] `tools/office/models.py` has Email, CalendarEvent, OfficeAccount models
- [ ] `tools/office/providers/base.py` defines abstract OfficeProvider
- [ ] `tools/office/providers/standalone_imap.py` can connect via IMAP
- [ ] `tools/office/oauth_manager.py` can initiate Google OAuth flow
- [ ] `tools/office/oauth_manager.py` can initiate Microsoft OAuth flow
- [ ] `tools/office/providers/google_workspace.py` can read inbox (Level 2)
- [ ] `tools/office/providers/microsoft_365.py` can read inbox (Level 2)
- [ ] `tools/office/email/reader.py` provides unified interface
- [ ] `tools/office/email/summarizer.py` generates inbox summary
- [ ] `tools/office/calendar/reader.py` retrieves events
- [ ] `tools/office/level_detector.py` correctly identifies level from scopes
- [ ] `tools/office/onboarding.py` wizard works in TUI
- [ ] `args/office_integration.yaml` has sensible defaults
- [ ] Database tables created on first use
- [ ] OAuth tokens stored encrypted in vault

---

## Phase 12b: Collaborative (Planned)

### Objective

Enable Level 3 functionality—creating drafts and scheduling meetings.

### New Tools

```
tools/office/email/
└── draft_manager.py               # Create/update/delete drafts

tools/office/calendar/
└── scheduler.py                   # Create/modify meetings
```

### Key Features

1. **Draft Creation**
   - Creates draft in user's mailbox (Gmail Drafts / Outlook Drafts)
   - Draft appears ready for user review
   - User clicks Send in their email client

2. **Meeting Scheduling**
   - Creates meeting with user as organizer
   - Sends invites from user's identity
   - Internal meetings can be auto-created (configurable)

3. **Sub-level Support**
   - 3a: Drafts only
   - 3b: Drafts + internal auto-send
   - 3c: Drafts + template auto-send

### Verification Checklist

- [ ] Draft appears in Gmail Drafts folder
- [ ] Draft appears in Outlook Drafts folder
- [ ] Meeting invite sent with user as organizer
- [ ] Attendees receive invite from user's address
- [ ] Dashboard shows pending drafts for review

---

## Phase 12c: Managed Proxy (Planned)

### Objective

Enable Level 4 functionality—full actions with undo capability and audit trail.

### New Tools

```
tools/office/actions/
├── __init__.py
├── queue.py                       # Action queue management
├── executor.py                    # Execute queued actions
├── undo_manager.py                # Undo window management
└── audit_logger.py                # Permanent action log

tools/office/email/
└── sender.py                      # Send emails (with undo)
```

### Database Additions

```sql
-- Action queue (for undo capability)
CREATE TABLE IF NOT EXISTS office_actions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL,        -- 'send_email', 'delete_email', 'schedule_meeting', etc.
    action_data TEXT NOT NULL,        -- JSON payload
    status TEXT DEFAULT 'pending',    -- 'pending', 'executed', 'undone', 'expired'
    undo_deadline DATETIME,
    executed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);

-- Audit log (permanent record)
CREATE TABLE IF NOT EXISTS office_audit_log (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_summary TEXT,
    action_data TEXT,                 -- JSON (may be redacted)
    result TEXT,                      -- 'success', 'failed', 'undone'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);
```

### Key Features

1. **Undo Window**
   - All actions queued with undo deadline
   - 60-second window (configurable)
   - Undo via dashboard, channel command, or API

2. **Audit Trail**
   - Every action logged permanently
   - Includes who, what, when, result
   - Export capability for compliance

3. **Daily Digest**
   - Summary of all Dex actions
   - Sent via configured notification channel
   - Helps ADHD users stay aware without micromanaging

### Verification Checklist

- [ ] Email sends after undo window expires
- [ ] Undo within window prevents send
- [ ] Audit log records all actions
- [ ] Daily digest notification sent
- [ ] Dashboard shows action history

---

## Phase 12d: Autonomous (Planned)

### Objective

Enable Level 5 functionality—policy-based autonomous actions.

### New Tools

```
tools/office/policies/
├── __init__.py
├── engine.py                      # Policy evaluation
├── parser.py                      # Parse policy YAML/JSON
└── defaults.py                    # Default policy templates

tools/office/email/
└── auto_responder.py              # Autonomous email responses

tools/office/calendar/
└── auto_scheduler.py              # Autonomous scheduling
```

### Database Additions

```sql
-- Policies (Level 5)
CREATE TABLE IF NOT EXISTS office_policies (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    name TEXT NOT NULL,
    policy_type TEXT NOT NULL,        -- 'inbox', 'calendar', 'response'
    conditions TEXT NOT NULL,         -- JSON conditions
    actions TEXT NOT NULL,            -- JSON actions
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES office_accounts(id)
);
```

### Key Features

1. **Policy Engine**
   - Condition-action rules
   - Priority ordering
   - Conflict resolution

2. **Example Policies**
   ```yaml
   - name: "Auto-archive newsletters"
     conditions:
       from_domain: ["substack.com", "mailchimp.com"]
       age_days: 7
       is_read: false
     actions:
       - archive

   - name: "VIP immediate notify"
     conditions:
       from: ["boss@company.com", "spouse@gmail.com"]
     actions:
       - notify_immediately
       - ignore_flow_state

   - name: "Protect focus time"
     conditions:
       event_type: "meeting_request"
       during: "focus_blocks"
     actions:
       - decline
       - suggest_alternatives
   ```

3. **Progressive Trust Gate**
   - Cannot jump directly to Level 5
   - Must use Level 4 for 90 days
   - Explicit acknowledgment of risks

4. **Emergency Pause**
   - One-click disable all autonomous actions
   - Accessible from dashboard + channel command
   - Auto-notifies user when triggered

### Verification Checklist

- [ ] Policy triggers on matching email
- [ ] Auto-response sent for configured patterns
- [ ] Auto-schedule respects availability
- [ ] Emergency pause stops all automation
- [ ] Progressive trust gate enforced
- [ ] Cannot skip from Level 2 to Level 5

---

## Security Considerations

### Token Storage

- All OAuth tokens encrypted in vault
- Token refresh handled automatically
- Revocation clears vault entries

### Scope Minimization

- Request only scopes needed for current level
- Never request Level 5 scopes for Level 2 user
- Explain each scope during onboarding

### Audit & Compliance

- All actions logged permanently
- Export to CSV/JSON for compliance
- Retention configurable per organization

### Revocation

User can revoke access via:
1. Dashboard "Disconnect" button
2. Google/Microsoft account settings
3. Emergency channel command (`!revoke office`)

---

## ADHD Design Principles Applied

| Principle | Implementation |
|-----------|----------------|
| **Zero-maintenance** | Autonomous actions work when user forgets |
| **Extended undo** | 60s window protects against impulsivity |
| **Sentiment detection** | Prevents regretted emotional sends |
| **Progressive trust** | Build confidence gradually, not all at once |
| **Single-action** | "What should I reply to?" returns ONE email |
| **No guilt** | Daily digest is informational, not judgmental |
| **Emergency escape** | Pause button when overwhelmed |

---

## Dependencies

- **Phase 0 (Security):** Vault for token storage
- **Phase 7 (Dashboard):** OAuth callback routes, settings UI
- **Phase 8 (Setup Wizard):** Onboarding patterns

---

*This document is a living tactical guide. Update as implementation progresses.*
