# DexAI Future Development Roadmap

> Planned phases for DexAI beyond the initial MVP. Each phase is designed with ADHD users as the primary consideration.

---

## Phase 10: Mobile Push Notifications

**Objective:** Real-time alerts on mobile devices

### Components

| Component | Description |
|-----------|-------------|
| **Firebase Cloud Messaging (FCM)** | Push notifications for Android devices |
| **Apple Push Notification Service (APNs)** | Push notifications for iOS devices |
| **Notification Preferences** | Per-user configuration for notification types, timing, and frequency |
| **Smart Batching** | Group related notifications to prevent notification fatigue |

### ADHD Considerations

- **Respect flow state:** Check flow protection status before sending non-urgent notifications
- **Gentle reminders:** Use supportive language, avoid guilt-inducing "you missed..." phrasing
- **Configurable urgency thresholds:** Let users define what's truly interrupt-worthy
- **Quiet hours:** Automatic DND during sleep/focus periods

### Technical Notes

- Requires mobile app development (React Native or Flutter)
- Server-side notification queue with priority levels
- Integration with existing `smart_notify.py` and `flow_protection.py`

---

## Phase 11: Voice Interface

**Objective:** Hands-free task capture and queries

### Components

| Component | Description |
|-----------|-------------|
| **Speech-to-Text** | Whisper API or browser Web Speech API for voice input |
| **Voice Command Parser** | NLP to extract intent and entities from spoken commands |
| **Text-to-Speech** | Response synthesis for audio feedback |
| **Wake Word Detection** | Optional "Hey Dex" trigger (privacy-conscious, on-device) |

### ADHD Considerations

- **Quick capture when hands are busy:** "Dex, remind me to call mom tomorrow"
- **Reduce friction:** Voice is faster than typing for ADHD brains in motion
- **Confirmation without interruption:** Gentle audio feedback, no screen required
- **Ambient listening opt-in only:** Respect privacy, default to push-to-talk

### Technical Notes

- Web Speech API for browser-based MVP (no cost)
- Whisper API for higher accuracy (requires API credits)
- Consider local Whisper model for privacy-sensitive users

---

## Phase 12: Office Integration (Expanded)

**Objective:** Comprehensive integration with Microsoft 365 and Google Workspace ecosystems

**Status:** 🔄 IN PROGRESS (Phase 12a)

Phase 12 has been expanded from simple "Calendar Integration" to full **Office Integration** covering email, calendar, and future office ecosystem features across 5 integration levels.

> **Detailed exploration:** `context/office_integration_exploration.md`
> **Implementation guide:** `goals/phase12_office_integration.md`

### Sub-Phases

| Sub-Phase | Name | Description | Status |
|-----------|------|-------------|--------|
| **12a** | Foundation | OAuth infrastructure, Level 1-2 (read-only) | 🔄 In Progress |
| **12b** | Collaborative | Level 3 (drafts, meeting scheduling) | 📋 Planned |
| **12c** | Managed Proxy | Level 4 (send with undo, audit trail) | 📋 Planned |
| **12d** | Autonomous | Level 5 (policy-based automation) | 📋 Planned |

### Integration Levels

```
LEVEL 5: TOTAL INTEGRATION (Full Agent)
    ↑ More power, more risk, more automation
    |
LEVEL 4: MANAGED PROXY (Supervised Agent)
    |
LEVEL 3: COLLABORATIVE ACCESS (Shared Control)
    |
LEVEL 2: READ + SUGGEST (Observer + Advisor)
    |
LEVEL 1: SANDBOXED PRESENCE (Own Identity)
    ↓ Less risk, more friction, more manual work
```

| Level | Name | Email | Calendar | Risk | ADHD Friction |
|-------|------|-------|----------|------|---------------|
| 1 | Sandboxed | Dex's own | Dex's own | Very Low | High |
| 2 | Read-Only | Read user's | Read user's | Low | Medium |
| 3 | Collaborative | Drafts | Schedule as user | Medium | Low |
| 4 | Managed Proxy | Send with undo | Full control | Medium-High | Very Low |
| 5 | Autonomous | Policy-based | Auto-manage | High | Minimal |

### Phase 12a: Foundation (Current)

**Deliverables:**
- OAuth flows for Google Workspace and Microsoft 365
- Level 1: Standalone IMAP/SMTP for Dex's own mailbox
- Level 2: Read-only access to user's inbox and calendar
- Integration level onboarding wizard
- Email summarization and calendar queries

**Tools Being Built:**
```
tools/office/
├── __init__.py                 # Path constants
├── models.py                   # Email, CalendarEvent, etc.
├── oauth_manager.py            # OAuth flows for Google + Microsoft
├── level_detector.py           # Determine current integration level
├── onboarding.py               # Integration level selection wizard
├── providers/
│   ├── base.py                 # Abstract provider interface
│   ├── google_workspace.py     # Gmail, Calendar APIs
│   ├── microsoft_365.py        # Graph API
│   └── standalone_imap.py      # Level 1: Dex's own mailbox
├── email/
│   ├── reader.py               # Inbox reading, search
│   └── summarizer.py           # Inbox summary generation
└── calendar/
    └── reader.py               # Read events, availability
```

### Phase 12b: Collaborative (Planned)

**Deliverables:**
- Draft creation in user's mailbox (appears in Drafts folder)
- Meeting scheduling with user as organizer
- Internal auto-send option (company domain only)
- Draft review UI in dashboard

**New Tools:**
- `tools/office/email/draft_manager.py`
- `tools/office/calendar/scheduler.py`

### Phase 12c: Managed Proxy (Planned)

**Deliverables:**
- Full email sending with undo window
- Action queue for all office operations
- Comprehensive audit trail
- Daily action digest notification
- Granular permission matrix

**New Tools:**
- `tools/office/actions/queue.py`
- `tools/office/actions/executor.py`
- `tools/office/actions/undo_manager.py`
- `tools/office/actions/audit_logger.py`
- `tools/office/email/sender.py`

### Phase 12d: Autonomous (Planned)

**Deliverables:**
- Policy engine for rule-based automation
- Auto-responder for configured patterns
- Auto-scheduler based on availability and preferences
- Progressive trust unlock (30-day gate)
- Emergency pause functionality

**New Tools:**
- `tools/office/policies/engine.py`
- `tools/office/policies/parser.py`
- `tools/office/email/auto_responder.py`
- `tools/office/calendar/auto_scheduler.py`

### ADHD-Specific Features (All Phases)

| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| **Extended Undo** | 60-second undo window (vs typical 30s) | ADHD impulsivity needs longer safety net |
| **Sentiment Detection** | Flag emotional emails for review | Prevent sending regretful messages |
| **Daily Digest** | "Here's what Dex did today" | Visibility without micromanagement |
| **Batch Confirmation** | Group similar actions | Reduce confirmation fatigue |
| **Emergency Pause** | One-click disable all autonomous actions | Instant safety when overwhelmed |
| **Cool-Off Period** | 10-minute delay for negative replies | Prevent RSD-driven responses |
| **Progressive Trust** | Unlock higher levels after proven usage | Build confidence gradually |

### Technical Architecture

**OAuth Scopes by Level:**
```yaml
level_1:
  google: []  # No user account access
  microsoft: []

level_2:
  google:
    - gmail.readonly
    - calendar.readonly
  microsoft:
    - Mail.Read
    - Calendars.Read

level_3:
  google:
    - gmail.modify  # Includes drafts
    - calendar
  microsoft:
    - Mail.ReadWrite
    - Calendars.ReadWrite

level_4:
  google:
    - gmail.modify
    - gmail.send
    - calendar
  microsoft:
    - Mail.ReadWrite
    - Mail.Send
    - Calendars.ReadWrite

level_5:
  google:
    - gmail.modify
    - gmail.send
    - calendar
    - contacts
  microsoft:
    - Mail.ReadWrite
    - Mail.Send
    - Calendars.ReadWrite
    - Contacts.ReadWrite
```

**Database Schema:**
- `office_accounts`: OAuth tokens and integration level
- `office_actions`: Action queue with undo capability
- `office_audit_log`: Permanent action record
- `office_policies`: Level 5 automation rules

### Security Considerations

- OAuth tokens encrypted in vault
- Minimal scope requests per level
- Action audit trail for accountability
- Rate limiting on API calls
- Revocation accessible from dashboard + emergency channel command

---

## Phase 13: Collaborative Features

**Objective:** Accountability partnerships for external motivation

### Components

| Component | Description |
|-----------|-------------|
| **Shared Task Visibility** | Opt-in sharing of specific tasks with accountability partners |
| **Body Doubling Sessions** | Virtual co-working with presence indicators |
| **Accountability Partner Notifications** | Alert partners when tasks are completed (celebration) or stuck (support) |
| **Progress Sharing** | Weekly digest to partners (if enabled) |

### ADHD Considerations

- **External accountability without shame:** Frame as support, not surveillance
- **Celebration over criticism:** Partners see completions, not failures
- **Body doubling for hard tasks:** ADHD brains work better with others present
- **Opt-in granularity:** Share specific tasks, not everything

### Technical Notes

- Partner invitation and linking system
- Presence/status indicators (working, on break, done for day)
- Consider integration with Discord/Slack for body doubling

---

## Phase 14: Analytics & Insights

**Objective:** Help users understand their patterns without judgment

### Components

| Component | Description |
|-----------|-------------|
| **Weekly/Monthly Reports** | Summarize productivity patterns, energy trends, wins |
| **Pattern Visualization** | Charts showing time-of-day effectiveness, task completion curves |
| **Personalized Recommendations** | Actionable suggestions based on learned patterns |
| **Trend Analysis** | Long-term improvement tracking |

### ADHD Considerations

- **Celebrate wins:** Lead with accomplishments, not deficits
- **No guilt-inducing comparisons:** Compare only to self, never to others or "ideal" metrics
- **Actionable insights:** "You complete 40% more tasks before noon" not just "completion rate: 60%"
- **Opt-out of tracking:** Some users prefer not to know; respect that

### Technical Notes

- Build on existing `energy_tracker.py` and `pattern_learner.py`
- Dashboard widgets in `frontend/` for visualizations
- Export to PDF for therapy/coaching sessions

---

## Future Considerations (Post-Phase 14)

These are ideas that may be explored after the core roadmap:

| Idea | Description |
|------|-------------|
| **Wearable Integration** | Smartwatch notifications, heart rate for stress detection |
| **Medication Reminders** | Sensitive handling of ADHD medication schedules |
| **Therapist/Coach Portal** | Read-only view for healthcare providers (user-controlled) |
| **AI Coaching** | Conversational support for emotional regulation |
| **Community Features** | Anonymous ADHD community tips and wins |

---

## Implementation Priority

Recommended order based on user impact and technical dependencies:

1. **Phase 12 (Office Integration)** — 🔄 IN PROGRESS — High user demand, comprehensive office support
2. **Phase 10 (Mobile Push)** — Requires mobile app, but high engagement value
3. **Phase 14 (Analytics)** — Builds on existing data, low risk
4. **Phase 11 (Voice)** — Nice-to-have, good accessibility feature
5. **Phase 13 (Collaboration)** — Valuable but complex, save for later

---

*Last updated: 2026-02-03*
*This roadmap is subject to change based on user feedback and technical discoveries.*
