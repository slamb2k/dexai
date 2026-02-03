# Office Integration Exploration

> Design exploration for DexAI integration with Microsoft 365 and Google Workspace ecosystems.

**Status:** Draft — Exploring options
**Author:** Claude + User
**Date:** 2026-02-03

---

## Executive Summary

DexAI can integrate with office ecosystems at varying depths. This document explores the spectrum from **Total Integration** (full inbox/calendar access) to **Sandboxed Presence** (Dex has its own identity). The right level depends on user trust, ADHD needs, and risk tolerance.

**Key Insight:** ADHD users may benefit MORE from deeper integration (less manual work, more automation) but also need MORE safeguards (undo windows, confirmation for destructive actions).

---

## The Integration Spectrum

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

---

## Level 1: Sandboxed Presence

**Concept:** Dex has its own email address and calendar. It can only see what users explicitly share or forward.

### Access Model

| Component | Read | Write | Delete | On Behalf Of |
|-----------|------|-------|--------|--------------|
| User's Email | ❌ | ❌ | ❌ | ❌ |
| User's Calendar | ❌ | ❌ | ❌ | ❌ |
| Dex's Email | ✅ | ✅ | ✅ | N/A |
| Dex's Calendar | ✅ | ✅ | ✅ | N/A |

### How It Works

- User creates `dex@company.com` or `dex.assistant@gmail.com`
- User forwards emails to Dex: "Hey Dex, handle this"
- User CCs Dex on threads to keep it informed
- Dex sends emails from its own address
- Dex creates calendar invites from its own identity (user accepts/declines)

### Use Cases

| Task | How It Works |
|------|--------------|
| "Remind me about this email" | User forwards → Dex tracks → Dex emails reminder |
| "Schedule a meeting with Sarah" | Dex sends invite from dex@company.com, CCs user |
| "Draft a reply" | Dex emails draft to user → User copy-pastes |
| "Summarize my inbox" | ❌ Not possible without forwarding |

### Pros

- **Maximum privacy** — Dex only sees explicitly shared content
- **Clear identity separation** — Recipients know Dex sent it
- **Low risk** — Cannot accidentally delete user's mail
- **Works with any email provider** — No API integration needed

### Cons

- **High friction** — User must manually forward/CC everything
- **No proactive assistance** — Can't surface important emails user missed
- **ADHD-unfriendly** — Requires consistent manual behavior (ADHD kryptonite)
- **No calendar visibility** — Can't suggest times based on availability

### ADHD Considerations

⚠️ **This level may be counterproductive for ADHD users.** The manual forwarding requirement is exactly the kind of "small friction" that ADHD brains skip, meaning Dex would be underutilized.

### Technical Implementation

```yaml
# Simple: Just email protocols
- IMAP/SMTP for Dex's own mailbox
- CalDAV for Dex's own calendar
- No OAuth to user accounts required
```

---

## Level 2: Read + Suggest (Observer + Advisor)

**Concept:** Dex can read the user's inbox and calendar but cannot take any actions. It observes and advises.

### Access Model

| Component | Read | Write | Delete | On Behalf Of |
|-----------|------|-------|--------|--------------|
| User's Email | ✅ | ❌ | ❌ | ❌ |
| User's Calendar | ✅ | ❌ | ❌ | ❌ |
| Dex's Email | ✅ | ✅ | ✅ | N/A |
| Dex's Calendar | ✅ | ✅ | ✅ | N/A |

### How It Works

- Dex connects via read-only OAuth scopes
- Dex monitors inbox and surfaces important items
- Dex suggests replies but cannot send them
- Dex identifies scheduling conflicts but cannot resolve them
- All actions require user execution

### Use Cases

| Task | How It Works |
|------|--------------|
| "Remind me about this email" | Dex already saw it → Auto-tracks → Notifies via channel |
| "Summarize my inbox" | ✅ Dex reads all → Provides summary |
| "Draft a reply" | Dex drafts → Shows in dashboard/channel → User sends manually |
| "Schedule a meeting" | Dex suggests times based on calendar → Sends invite from Dex identity |
| "What's on my calendar today?" | ✅ Full visibility |

### Pros

- **Proactive awareness** — Dex can surface emails user forgot about
- **Low action risk** — Cannot send/delete on user's behalf
- **ADHD-helpful** — "What did I miss?" queries work
- **Calendar intelligence** — Knows availability for scheduling

### Cons

- **Execution friction** — User must still manually send/delete
- **Privacy exposure** — Dex sees all email content
- **Limited automation** — Cannot fully handle routine tasks

### ADHD Considerations

✅ **Good balance for users who want awareness without automation risk.**
Dex can be the "second brain" that notices things, but the user stays in control of actions. However, the "Dex noticed but user didn't act" scenario is still a failure mode.

### Technical Implementation

```yaml
# Google Workspace
scopes:
  - https://www.googleapis.com/auth/gmail.readonly
  - https://www.googleapis.com/auth/calendar.readonly

# Microsoft 365
permissions:
  - Mail.Read
  - Calendars.Read
```

---

## Level 3: Collaborative Access (Shared Control)

**Concept:** Dex can read everything and write *some* things. Destructive actions (delete, send external) require confirmation.

### Access Model

| Component | Read | Write | Delete | On Behalf Of |
|-----------|------|-------|--------|--------------|
| User's Email | ✅ | ✅ (drafts) | ❌ | ❌ (needs confirm) |
| User's Calendar | ✅ | ✅ (create) | ❌ | ✅ (internal only) |
| Shared Drafts | ✅ | ✅ | ✅ | N/A |

### How It Works

- Dex can create drafts in user's mailbox (user reviews before sending)
- Dex can schedule meetings on user's calendar (with user as organizer)
- Dex CANNOT delete emails or cancel meetings
- Dex CANNOT send external emails without explicit per-message approval
- Dex CAN auto-respond to internal/known contacts with templates

### Permission Tiers Within Level 3

```
3a: Drafts Only
    - Create drafts user reviews
    - No sending capability

3b: Internal Auto-Send
    - Auto-send to @company.com addresses
    - Drafts for external contacts

3c: Template Auto-Send
    - Auto-send pre-approved templates to anyone
    - Drafts for custom content
```

### Use Cases

| Task | How It Works |
|------|--------------|
| "Reply to Sarah's email" | Dex creates draft in Outlook/Gmail → User reviews → User clicks send |
| "Schedule standup with team" | Dex creates invite as user → Sends immediately (internal) |
| "Send my standard OOO reply" | Dex sends template (3c) or creates draft (3a) |
| "Archive processed emails" | ❌ Archive = move/label, allowed. Delete = blocked. |

### Pros

- **Significant time savings** — Drafts appear ready to review
- **Safe defaults** — Destructive actions blocked
- **Flexible sub-levels** — User chooses comfort zone
- **ADHD-optimized** — Reduces "just draft a reply" procrastination

### Cons

- **Review burden** — User must still approve drafts (though lower friction)
- **Partial automation** — "Schedule and confirm" workflows incomplete
- **Complexity** — Multiple sub-levels to configure

### ADHD Considerations

✅ **Strong choice for ADHD users.** The "draft appears magically" pattern reduces the activation energy of email replies. The "no delete" guardrail prevents impulsive purges.

**Caution:** Some ADHD users may ignore drafts folder, creating phantom progress.

### Technical Implementation

```yaml
# Google Workspace
scopes:
  - https://www.googleapis.com/auth/gmail.modify  # NOT gmail.compose (send)
  - https://www.googleapis.com/auth/calendar

# Microsoft 365
permissions:
  - Mail.ReadWrite  # Drafts yes, send no
  - Calendars.ReadWrite
```

---

## Level 4: Managed Proxy (Supervised Agent)

**Concept:** Dex acts as user's proxy with full capabilities but under supervision. Actions are logged, reversible, and optionally require confirmation.

### Access Model

| Component | Read | Write | Delete | On Behalf Of |
|-----------|------|-------|--------|--------------|
| User's Email | ✅ | ✅ | ✅* | ✅ |
| User's Calendar | ✅ | ✅ | ✅* | ✅ |

*Soft delete with undo window; hard delete requires confirmation

### How It Works

- Dex has full OAuth access to act as user
- All actions logged in audit trail with undo capability
- **Undo Window:** Actions can be reversed for configurable period (e.g., 30 seconds for sends, 24 hours for deletes)
- **Confirmation Modes:**
  - Auto with notification (action happens, user notified)
  - Auto with undo (action happens, undo button available)
  - Confirm before (action queued, user approves batch)
  - Block (specific action types always require confirmation)

### Permission Matrix (User Configurable)

| Action | Auto | Auto + Notify | Auto + Undo | Confirm | Block |
|--------|------|---------------|-------------|---------|-------|
| Send internal | ○ | ● | ○ | ○ | ○ |
| Send external | ○ | ○ | ● | ○ | ○ |
| Delete email | ○ | ○ | ○ | ● | ○ |
| Accept meeting | ○ | ● | ○ | ○ | ○ |
| Decline meeting | ○ | ○ | ○ | ● | ○ |
| Cancel meeting | ○ | ○ | ○ | ○ | ● |

### Use Cases

| Task | How It Works |
|------|--------------|
| "Reply to Sarah" | Dex sends immediately → Notification appears → 30s undo window |
| "Clear my inbox of newsletters" | Dex batches deletions → User confirms batch → Executes |
| "Accept all meetings for this week" | Dex accepts → Notifications sent → User can undo individually |
| "Reschedule tomorrow's standup" | Dex sends reschedule → As user → Attendees see user as sender |

### Pros

- **Near-full automation** — Most tasks complete without user intervention
- **Safety through undo** — Mistakes recoverable
- **Audit trail** — Full visibility into what Dex did
- **Granular control** — User configures per-action behavior

### Cons

- **Requires trust** — User must accept AI sending as them
- **Reputation risk** — Poorly worded auto-reply reflects on user
- **Configuration complexity** — Many knobs to tune
- **Undo pressure** — 30-second undo window requires attention

### ADHD Considerations

✅ **Potentially transformative for ADHD users** who struggle with email/calendar maintenance. The "it just happens" model matches ADHD need for reduced friction.

⚠️ **Risk:** ADHD impulsivity + auto-confirm could lead to regretted sends. **Mitigation:** Longer undo windows, "cooling off" period for emotional emails (sentiment detection).

**Recommended ADHD defaults:**
- 60-second undo window (longer than typical 30s)
- Sentiment check on replies (flag angry/stressed tone for review)
- Daily digest of all Dex actions ("here's what I did today")

### Technical Implementation

```yaml
# Full access required
# Google Workspace
scopes:
  - https://www.googleapis.com/auth/gmail.modify
  - https://www.googleapis.com/auth/gmail.send
  - https://www.googleapis.com/auth/calendar

# Microsoft 365
permissions:
  - Mail.ReadWrite
  - Mail.Send
  - Calendars.ReadWrite

# DexAI additional infrastructure
- Action queue with undo capability
- Audit log database
- Undo webhook/API for quick reversals
- Notification delivery system (channels)
```

---

## Level 5: Total Integration (Full Agent)

**Concept:** Dex is a fully autonomous agent with complete control over email and calendar. It acts proactively without confirmation.

### Access Model

| Component | Read | Write | Delete | On Behalf Of | Autonomous |
|-----------|------|-------|--------|--------------|------------|
| User's Email | ✅ | ✅ | ✅ | ✅ | ✅ |
| User's Calendar | ✅ | ✅ | ✅ | ✅ | ✅ |
| Contacts | ✅ | ✅ | ✅ | ✅ | ✅ |
| Files/Drive | ✅ | ✅ | ✅ | ✅ | ✅ |

### How It Works

- Dex has standing permission to manage all office functions
- Dex proactively manages inbox (auto-archive, auto-respond, auto-sort)
- Dex proactively manages calendar (auto-decline conflicts, auto-reschedule)
- Dex acts on learned preferences without per-action confirmation
- User sets policies; Dex executes within policies

### Policy Examples

```yaml
inbox_policies:
  - name: "Newsletter auto-archive"
    condition: "from domain in [substack.com, mailchimp.com]"
    action: "archive after 7 days if unread"

  - name: "VIP immediate notify"
    condition: "from in [boss@company.com, spouse@personal.com]"
    action: "notify immediately regardless of flow state"

  - name: "Meeting request auto-handle"
    condition: "meeting invite AND availability exists"
    action: "tentatively accept, notify user"

calendar_policies:
  - name: "Protect focus time"
    condition: "meeting request during focus blocks"
    action: "decline with message: 'This time is blocked for focused work. Here are alternatives: [suggest times]'"

  - name: "Auto-reschedule conflicts"
    condition: "double-booked AND one is internal"
    action: "reschedule internal meeting to next available slot"
```

### Use Cases

| Task | How It Works |
|------|--------------|
| Inbox management | Dex continuously processes, user sees curated view |
| Meeting scheduling | Dex handles all logistics, user just shows up |
| Email responses | Dex drafts and sends routine replies autonomously |
| Information requests | Dex answers on behalf of user using knowledge base |

### Pros

- **Maximum time savings** — User offloads entire email/calendar burden
- **Consistent behavior** — Dex always responds, never forgets
- **Proactive management** — Problems solved before user notices

### Cons

- **Maximum risk** — AI errors sent without review
- **Privacy concerns** — Full access to all communications
- **Trust requirement** — User must fully trust AI judgment
- **Accountability ambiguity** — Who's responsible for AI-sent emails?
- **Dependency risk** — User may lose email management skills

### ADHD Considerations

🤔 **Double-edged sword for ADHD users.**

**Benefits:**
- Removes email as a source of anxiety
- Ensures nothing falls through cracks
- Eliminates "email bankruptcy" cycles

**Risks:**
- ADHD impulsivity may lead to over-permissive policies
- Losing touch with communications could cause relationship issues
- Recovery if Dex makes mistakes could be overwhelming

**Recommendation:** Level 5 should require:
1. Successful use of Level 4 for 30+ days
2. Explicit "I understand the risks" acknowledgment
3. Mandatory weekly "Dex action review" in dashboard
4. Emergency "pause all autonomous actions" button

### Technical Implementation

```yaml
# Same as Level 4 plus:
# - Policy engine for rule evaluation
# - Continuous background processing
# - ML models for preference learning
# - Escalation logic for edge cases

# Additional scopes potentially needed:
# Google
  - https://www.googleapis.com/auth/contacts
  - https://www.googleapis.com/auth/drive

# Microsoft
  - Contacts.ReadWrite
  - Files.ReadWrite
```

---

## Comparison Matrix

| Capability | L1: Sandbox | L2: Read | L3: Collab | L4: Managed | L5: Total |
|------------|-------------|----------|------------|-------------|-----------|
| See user's inbox | ❌ | ✅ | ✅ | ✅ | ✅ |
| See user's calendar | ❌ | ✅ | ✅ | ✅ | ✅ |
| Create drafts | ❌ | ❌ | ✅ | ✅ | ✅ |
| Send as user | ❌ | ❌ | ⚠️ | ✅ | ✅ |
| Delete email | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Schedule meetings | Own ID | Own ID | User ID | User ID | User ID |
| Autonomous actions | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Risk level** | Very Low | Low | Medium | Medium-High | High |
| **ADHD friction** | High | Medium | Low | Very Low | Minimal |
| **Setup complexity** | Simple | Simple | Medium | Complex | Complex |

⚠️ = With confirmation/undo

---

## ADHD-Specific Recommendations

### Default Level by User Profile

| User Profile | Recommended Start | Why |
|--------------|-------------------|-----|
| Privacy-conscious | Level 2 | Awareness without action risk |
| New to AI assistants | Level 3a | Drafts only, builds trust |
| Comfortable with automation | Level 3c | Templates reduce friction |
| Power user / high trust | Level 4 | Full capability with safety net |
| Executive assistant replacement | Level 5 | Maximum delegation (with guardrails) |

### ADHD-Specific Safeguards (All Levels)

1. **Undo Windows** — Longer than neurotypical defaults (60s vs 30s)
2. **Sentiment Detection** — Flag emotional emails for review before send
3. **Daily Digest** — "Here's what Dex did today" summary
4. **Batch Confirmation** — Group similar actions for single approval
5. **Emergency Pause** — One-click disable all autonomous actions
6. **Cool-Off Period** — Delay sending replies to negative emails by 10 minutes

### Progressive Trust Model

```
Start: Level 2 (read-only)
    ↓ After 7 days of successful use
Unlock: Level 3 (collaborative)
    ↓ After 30 days + no major issues
Unlock: Level 4 (managed proxy)
    ↓ After 90 days + explicit request
Unlock: Level 5 (total integration)
```

---

## Technical Architecture

### OAuth Scopes by Level

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
    - drive
  microsoft:
    - Mail.ReadWrite
    - Mail.Send
    - Calendars.ReadWrite
    - Contacts.ReadWrite
    - Files.ReadWrite
```

### Required DexAI Infrastructure

| Component | L1 | L2 | L3 | L4 | L5 |
|-----------|----|----|----|----|----|----|
| Dex email account | ✅ | ⚪ | ⚪ | ⚪ | ⚪ |
| OAuth integration | ⚪ | ✅ | ✅ | ✅ | ✅ |
| Action queue | ⚪ | ⚪ | ⚪ | ✅ | ✅ |
| Undo system | ⚪ | ⚪ | ⚪ | ✅ | ✅ |
| Audit logging | ⚪ | ✅ | ✅ | ✅ | ✅ |
| Policy engine | ⚪ | ⚪ | ⚪ | ⚪ | ✅ |
| ML preference learner | ⚪ | ⚪ | ⚪ | ⚪ | ✅ |

⚪ = Optional  ✅ = Required

---

## Implementation Phases

### Recommended Build Order

1. **Phase 12a: Read Integration (Level 2)**
   - OAuth flows for Google and Microsoft
   - Email/calendar read APIs
   - "What's in my inbox?" and "What's on my calendar?" queries
   - Inbox summary and priority highlighting

2. **Phase 12b: Collaborative Access (Level 3)**
   - Draft creation in user's mailbox
   - Meeting scheduling as user
   - Template management
   - Internal auto-send (optional)

3. **Phase 12c: Managed Proxy (Level 4)**
   - Action queue with undo
   - Full send capability
   - Audit trail and daily digest
   - Granular permission configuration

4. **Phase 12d: Full Autonomy (Level 5)**
   - Policy engine
   - Continuous background processing
   - Preference learning
   - Escalation logic

---

## Security Considerations

### Data Handling

| Concern | Mitigation |
|---------|------------|
| Email content storage | Encrypt at rest, minimal retention |
| OAuth token security | Store in vault, rotate regularly |
| Action logging | Audit trail for accountability |
| Third-party access | Never share email content with external services |

### Scope Minimization

Request only the OAuth scopes needed for the user's chosen level. **Never request Level 5 scopes for a Level 2 user.**

### Revocation

User must be able to instantly revoke all access via:
1. Dashboard "Disconnect" button
2. Google/Microsoft account security settings
3. Emergency channel command ("!revoke office")

---

## Open Questions

1. **Shared mailboxes:** Should Dex access team/shared inboxes, or only personal?
2. **Multiple accounts:** Support for users with multiple Google/Microsoft accounts?
3. **Enterprise admin controls:** Should org admins be able to cap integration level?
4. **Legal/compliance:** Email auto-responses may have legal implications (contracts, commitments)
5. **Offline handling:** What happens when Dex can't reach the APIs?

---

## Next Steps

1. [ ] User feedback on level descriptions
2. [ ] Decide initial target level for Phase 12
3. [ ] Technical spike: OAuth flow implementation
4. [ ] Design: Integration level selector UI
5. [ ] Security review of scope requirements

---

*This document is a living exploration. Update as decisions are made.*
