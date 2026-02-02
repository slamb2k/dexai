# Product Requirements Document (PRD)
# DexAI: Personal Assistant for Neuro-Divergent Users

**Version:** 1.0
**Date:** 2026-02-02
**Status:** Active
**Owner:** Product Team

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-02 | Product Team | Initial PRD — pivot from addulting-ai to DexAI with ADHD focus |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Product Vision & Strategy](#3-product-vision--strategy)
4. [Target Users](#4-target-users)
5. [Core Design Principles](#5-core-design-principles)
6. [Feature Requirements](#6-feature-requirements)
7. [Technical Architecture](#7-technical-architecture)
8. [Release Roadmap](#8-release-roadmap)
9. [Success Metrics](#9-success-metrics)
10. [Risks & Mitigations](#10-risks--mitigations)
11. [Out of Scope](#11-out-of-scope)
12. [References](#12-references)

---

## 1. Executive Summary

### 1.1 Product Overview

**DexAI** is a zero-maintenance AI personal assistant designed specifically for neuro-divergent users, particularly those with ADHD and ADD. Unlike generic productivity tools that fail when users can't consistently operate them, DexAI is built to work even when forgotten for days — surfacing gently, never guilting, and actively reducing cognitive load rather than adding to it.

### 1.2 Key Differentiators

| Differentiator | Description |
|----------------|-------------|
| **Zero-Maintenance** | Works even if user forgets it exists for three days |
| **Emotionally Safe** | No guilt, no shame, no "overdue" counts — forward-facing only |
| **One-Thing Focus** | Presents single actionable items, not overwhelming lists |
| **External Working Memory** | Captures context on every switch, enables instant resumption |
| **Time-Blindness Aware** | Understands transition time, not just clock time |
| **Hyperfocus Protection** | Suppresses interruptions during productive flow states |

### 1.3 Core Philosophy

> Most productivity tools fail ADHD users because they're built on a neurotypical assumption: that the user has consistent executive function available to *operate the system itself*.

DexAI is different. Every feature is designed with the question: **"Will this still work if the user hasn't touched the system in a week?"**

### 1.4 Target Outcome

The ultimate measure of success isn't feature richness — it's whether **the user is still using DexAI six months later**. That requires the system to be effortless to maintain, emotionally safe to return to after absence, and genuinely reducing cognitive load.

---

## 2. Problem Statement

### 2.1 Why Productivity Tools Fail ADHD Users

| Problem | Impact | Why Tools Fail | DexAI Solution |
|---------|--------|----------------|----------------|
| **Executive function variance** | Can't consistently operate the tool | Assumes daily engagement | Zero-maintenance design |
| **Working memory limitations** | Context switches cost 20-45 min | No state capture | Auto-snapshot on every switch |
| **Time blindness** | Misses deadlines despite reminders | "15 min" reminders useless | Transition-time-aware nudges |
| **Decision fatigue** | Paralyzed by options | Lists of 5+ items | One-thing responses |
| **Rejection sensitivity (RSD)** | Avoids tool after perceived failure | "Overdue" counts, guilt language | Forward-facing, shame-free |
| **Hyperfocus interruption** | Destroys rare productive states | Constant notifications | Flow detection + suppression |
| **Object permanence issues** | Forgets commitments exist | No proactive surfacing | Gentle, persistent re-surfacing |

### 2.2 The ADHD App Graveyard

Every ADHD user has a graveyard of abandoned productivity apps:
- Downloaded with hope
- Used intensely for a week
- Missed a day, felt guilty
- Avoided the app to avoid the guilt
- Never opened again

**DexAI breaks this cycle** by being emotionally safe to return to at any time, with no accumulated guilt or "catching up" required.

### 2.3 Market Opportunity

- **8.7 million** adults in the US have ADHD (4.4% of population)
- **Growing awareness** — adult ADHD diagnoses up 123% from 2007-2016
- **Underserved market** — generic tools don't address neuro-divergent needs
- **High willingness to pay** — ADHD users will pay for tools that actually work

---

## 3. Product Vision & Strategy

### 3.1 Vision Statement

> **An AI assistant that thinks the way ADHD brains need, not the way neurotypical tools assume.**

DexAI doesn't just manage tasks — it acts as an external executive function system, handling the context-switching, time estimation, and decision-making that ADHD brains struggle with.

### 3.2 Strategic Principles

| Principle | Implementation |
|-----------|----------------|
| **Default to brevity** | One sentence outputs unless user asks for more |
| **Never guilt** | No "overdue," no "you still haven't," no shame |
| **One thing at a time** | Single actionable item, not prioritized lists |
| **Pre-solve friction** | Remove barriers before presenting tasks |
| **Protect flow states** | Suppress interruptions during hyperfocus |
| **Graceful degradation** | Re-engagement feels fresh, not like returning to a mess |

### 3.3 Positioning

```
For: Adults with ADHD/ADD who struggle with traditional productivity tools
DexAI is: A zero-maintenance AI assistant
That: Reduces cognitive load instead of adding to it
Unlike: Generic productivity apps that require consistent executive function
Because: It's built around how ADHD brains actually work
```

---

## 4. Target Users

### 4.1 Primary Persona: Alex (ADHD Professional)

**Demographics:** 32, software developer, diagnosed ADHD at 28

**Pain Points:**
- Has tried every todo app; all abandoned within a month
- Loses 30+ minutes every context switch re-orienting
- Forgets promises made in conversations, damaging relationships
- Overwhelmed by task lists, so avoids looking at them
- Feels crushing guilt when seeing "15 overdue items"

**Needs:**
- Something that works even when forgotten
- Help remembering where they left off
- Single next action, not lists
- No judgment for missed days
- Protection during hyperfocus periods

**Success looks like:** Still using DexAI daily after 6 months, without any "catch up" sessions needed.

### 4.2 Secondary Persona: Jordan (ADHD Student)

**Demographics:** 22, university student, recently diagnosed

**Pain Points:**
- Can't estimate how long things take (time blindness)
- Starts assignments night before due (hyperfocus cramming)
- Forgets appointments despite calendar entries
- Phone reminders become background noise

**Needs:**
- Transition-time-aware reminders ("start wrapping up")
- Task decomposition ("first step is...")
- Varied notification styles to prevent habituation
- Energy-appropriate task suggestions

### 4.3 Tertiary Persona: Morgan (ADHD Parent)

**Demographics:** 41, working parent, manages household

**Pain Points:**
- Drops balls on kids' school requirements
- Forgets to reply to important messages
- Can't keep track of recurring obligations
- Overwhelmed by mental load of household management

**Needs:**
- Relationship/commitment tracking
- Proactive surfacing of aging messages
- Recurring task handling without requiring setup
- "Where did I put that?" search capability

---

## 5. Core Design Principles

> **Full design principles documented in:** `context/adhd_design_principles.md`

### 5.1 Communication Design

| Principle | Implementation |
|-----------|----------------|
| Adaptive brevity | Default: 1 sentence. User can ask "more" for depth |
| RSD-safe tone | Never implies should-have, frames everything forward |
| One-thing responses | Single actionable item when asked "what should I do?" |

### 5.2 Notification Architecture

| Principle | Implementation |
|-----------|----------------|
| Transition time | Accounts for ADHD context-switch cost in timing |
| Persistent without pressure | Re-surfaces important things without guilt escalation |
| Hyperfocus protection | Detects flow states, suppresses non-urgent interrupts |
| Channel tiering | Silent/ambient/interrupt based on true priority |

### 5.3 External Working Memory

| Principle | Implementation |
|-----------|----------------|
| Context capture | Auto-snapshot on every switch (file, action, next step) |
| Instant resumption | "You were here, doing this, about to do that" |
| Commitment tracking | Surfaces promises, aging messages, forgotten contacts |
| Universal search | "Where did I put that spreadsheet from Tuesday?" |

### 5.4 Task Decomposition

| Principle | Implementation |
|-----------|----------------|
| Auto-breakdown | Decomposes ambiguous tasks proactively |
| Friction pre-solving | Identifies and removes barriers before presenting |
| Energy matching | Suggests tasks appropriate to current energy level |

### 5.5 Anti-Patterns (Never Do)

- ❌ Require daily check-ins
- ❌ Display overdue counts
- ❌ Require user to organize/tag
- ❌ Present more than 3 choices (2 better, 1 best)
- ❌ Make re-engagement feel like returning to a mess

---

## 6. Feature Requirements

### 6.1 Phase Overview

| Phase | Focus | Duration | Key Deliverable |
|-------|-------|----------|-----------------|
| 0 | Foundation | Complete | Security + Memory (done) |
| 1 | Channels | 4 weeks | Multi-platform messaging |
| 2 | Working Memory | 4 weeks | Context capture + resumption |
| 3 | Communication | 4 weeks | RSD-safe responses, one-thing mode |
| 4 | Notifications | 4 weeks | Time-blind-aware, hyperfocus protection |
| 5 | Task Engine | 4 weeks | Decomposition, friction-solving |
| 6 | Learning | 6 weeks | Energy patterns, personalization |
| 7 | Dashboard | 4 weeks | Web-based management interface |
| 8 | Installation | 2 weeks | Guided setup wizard (web + TUI) |

### 6.2 Phase 0: Foundation (COMPLETE)

**Status:** ✅ Done

| Feature | Tool | Status |
|---------|------|--------|
| Audit logging | `tools/security/audit.py` | ✅ |
| Encrypted secrets | `tools/security/vault.py` | ✅ |
| Input sanitization | `tools/security/sanitizer.py` | ✅ |
| Rate limiting | `tools/security/ratelimit.py` | ✅ |
| Session management | `tools/security/session.py` | ✅ |
| RBAC permissions | `tools/security/permissions.py` | ✅ |
| Persistent memory | `tools/memory/*` | ✅ |

### 6.3 Phase 1: Channels (IN PROGRESS)

**Objective:** Meet users where they are — messaging apps they already use.

| Feature | Priority | Tool |
|---------|----------|------|
| Unified message model | P0 | `tools/channels/models.py` ✅ |
| Message inbox | P0 | `tools/channels/inbox.py` ✅ |
| Channel router | P0 | `tools/channels/router.py` ✅ |
| Telegram adapter | P0 | `tools/channels/telegram.py` ✅ |
| Discord adapter | P1 | `tools/channels/discord.py` ✅ |
| Slack adapter | P1 | `tools/channels/slack.py` ✅ |
| WebSocket gateway | P1 | `tools/channels/gateway.py` ✅ |

### 6.4 Phase 2: External Working Memory

**Objective:** Eliminate context-switch cost — the killer feature for ADHD users.

| Feature | Priority | Description |
|---------|----------|-------------|
| Context snapshot | P0 | Auto-capture state on every switch |
| Resumption prompt | P0 | "You were here, doing this, next was..." |
| Commitment tracker | P0 | Track promises made in conversation |
| Message aging alerts | P1 | Surface unanswered messages (gently) |
| Contact freshness | P1 | Flag people not contacted in a while |
| Universal search | P1 | "Where did I put that file from Tuesday?" |

### 6.5 Phase 3: ADHD Communication Mode

**Objective:** Tone and style that's safe for rejection-sensitive brains.

| Feature | Priority | Description |
|---------|----------|-------------|
| Brevity default | P0 | One sentence unless expanded |
| RSD-safe language | P0 | Forward-facing, no shame |
| One-thing mode | P0 | Single action when asked "what should I do?" |
| Expandable depth | P1 | "Why?" and "more" to get details |
| Tone calibration | P1 | User can adjust warmth/directness |

### 6.6 Phase 4: Smart Notifications

**Objective:** Notifications that work with ADHD, not against it.

| Feature | Priority | Description |
|---------|----------|-------------|
| Transition time | P0 | Factor in context-switch cost |
| Hyperfocus detection | P0 | Detect flow states from patterns |
| Interrupt suppression | P0 | Queue non-urgent during flow |
| Gentle persistence | P1 | Re-surface without guilt escalation |
| Channel tiering | P1 | Silent/ambient/interrupt by priority |
| Snooze with memory | P1 | "I know about it" escape valve |

### 6.7 Phase 5: Task Engine

**Objective:** Do the executive function work the user can't.

| Feature | Priority | Description |
|---------|----------|-------------|
| Auto-decomposition | P0 | Break "do taxes" into first step |
| Current step only | P0 | Don't show full breakdown |
| Friction detection | P1 | Identify barriers to starting |
| Friction pre-solving | P1 | Remove barriers before presenting |
| Energy matching | P1 | Right task for current energy |

### 6.8 Phase 6: Learning & Personalization

**Objective:** Get better at predicting user needs over time.

| Feature | Priority | Description |
|---------|----------|-------------|
| Energy patterns | P1 | Learn peak/trough times |
| Predictive surfacing | P2 | Surface tasks before user asks |
| Communication adaptation | P2 | Learn preferred style |
| Progress visualization | P2 | Dopamine-friendly metrics (opt-in) |
| Novelty injection | P2 | Vary phrasing to prevent habituation |

### 6.9 Phase 7: Web Dashboard

**Objective:** Visual management interface for monitoring, configuring, and debugging DexAI.

> **Full specification:** `goals/phase7_dashboard.md`

| Feature | Priority | Description |
|---------|----------|-------------|
| Dex Avatar | P0 | Animated visual indicator of agent state (idle, thinking, working, etc.) |
| Task Timeline | P0 | Real-time view of current and completed task executions |
| Activity Feed | P0 | Live stream of all Dex actions and events |
| Quick Stats | P0 | Today's metrics: tasks, messages, cost |
| Metrics Dashboard | P1 | Usage analytics, cost tracking, performance charts |
| Audit Viewer | P1 | Searchable security and event logs |
| Configuration Panel | P1 | Manage settings through UI (no YAML editing) |
| Debug Console | P2 | Logs, database browser, health checks (admin only) |
| Memory Inspector | P2 | Browse and search persistent memory |

**Design Philosophy:**
- Dark, calm aesthetic (Modal.com-inspired)
- Black/blue color palette with subtle glows
- Immediate visual feedback reduces ADHD anxiety ("is it working?")
- Clean, uncluttered — information density without overwhelm

**Technology Stack:** Next.js 14, Tailwind CSS, shadcn/ui, Recharts, Socket.IO

### 6.10 Phase 8: Guided Installation

**Objective:** Zero-friction onboarding that gets users to first successful interaction in minutes.

> **Full specification:** `goals/phase8_installation.md`

| Feature | Priority | Description |
|---------|----------|-------------|
| Web Wizard | P0 | Browser-based setup flow with visual guidance |
| TUI Wizard | P0 | Terminal-based setup for CLI users |
| Channel Setup | P0 | Guided connection for Telegram, Discord, Slack |
| Credential Storage | P0 | Secure API key and token management |
| Progress Persistence | P1 | Resume interrupted setup |
| Connection Testing | P1 | Verify each channel works before proceeding |
| First Interaction | P1 | Guided test message to confirm everything works |
| Setup Guides | P2 | Detailed per-channel documentation with screenshots |

**Design Philosophy:**
- Progressive disclosure — one thing at a time
- Smart defaults — configure later, not during setup
- Immediate feedback — test each step before continuing
- ADHD-friendly — no walls of text, clear progress indicators

**Technology Stack:** Textual (TUI), Next.js (web), existing channel adapters

---

## 7. Technical Architecture

### 7.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        DexAI Core                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Telegram│  │ Discord │  │  Slack  │  │ Gateway │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       └────────────┼───────────┴───────────┬┘              │
│                    ▼                                        │
│              ┌──────────┐                                   │
│              │  Router  │ ← Unified message handling        │
│              └────┬─────┘                                   │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Security Pipeline                       │   │
│  │  Sanitize → Authenticate → Rate Limit → Authorize   │   │
│  └─────────────────────────────────────────────────────┘   │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ADHD Intelligence Layer                 │   │
│  │  Context Capture | RSD-Safe Response | Task Engine  │   │
│  └─────────────────────────────────────────────────────┘   │
│                   ▼                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ Memory  │  │ Notify  │  │Scheduler│  │ Triggers│       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Language | Python 3.11+ | Ecosystem, async support |
| Database | SQLite | Local-first, zero-config |
| LLM | Claude API | Best at nuanced, empathetic responses |
| Messaging | Platform SDKs | Native integration |
| Automation | asyncio + croniter | Lightweight, no external deps |

### 7.3 Directory Structure

```
dexai/
├── tools/
│   ├── security/      # Auth, audit, permissions
│   ├── channels/      # Messaging adapters
│   ├── memory/        # Persistent memory
│   ├── automation/    # Scheduler, heartbeat, notifications
│   └── adhd/          # ADHD-specific intelligence (Phase 2-5)
├── args/              # Configuration
├── context/           # Design principles, research
├── goals/             # PRD, phase plans
├── hardprompts/       # LLM instruction templates
├── data/              # SQLite databases
└── memory/            # Persistent user memory
```

### 7.4 Data Models

**Context Snapshot** (Phase 2)
```python
@dataclass
class ContextSnapshot:
    id: str
    timestamp: datetime
    active_file: Optional[str]
    last_action: str
    likely_next_step: str
    open_tabs: List[str]
    mental_context: str  # LLM-generated summary
```

**Commitment** (Phase 2)
```python
@dataclass
class Commitment:
    id: str
    user_id: str
    made_to: str
    content: str
    source_message_id: str
    made_at: datetime
    due_at: Optional[datetime]
    status: str  # pending, completed, surfaced
```

---

## 8. Release Roadmap

### 8.1 Timeline

```
2026
├── Feb: Phase 0 Complete (Security + Memory) ✅
├── Mar: Phase 1 Complete (Channels) 🔄
├── Apr: Phase 2 (External Working Memory)
├── May: Phase 3 (ADHD Communication Mode)
├── Jun: Phase 4 (Smart Notifications)
├── Jul: Phase 5 (Task Engine)
├── Aug-Sep: Phase 6 (Learning)
├── Oct: Phase 7 (Web Dashboard)
└── Nov: Phase 8 (Guided Installation)

Dec 2026: Public Beta
```

### 8.2 Release Criteria

| Milestone | Criteria |
|-----------|----------|
| Alpha | Core messaging works, basic memory, founder testing |
| Beta | All P0 features, context capture working, 10 ADHD beta users |
| GA | 6-month retention >50%, user-reported cognitive load reduction |

---

## 9. Success Metrics

### 9.1 Primary Metric

> **6-Month Retention Rate** — The percentage of users still actively using DexAI after 6 months.

**Target:** >50% (vs. industry average ~10% for productivity apps)

### 9.2 Supporting Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Re-engagement after gap | >80% | Users return after 3+ days away |
| Context resumption usage | >70% | Killer feature adoption |
| Overdue count | 0 | We never show this |
| Guilt language instances | 0 | RSD-safe compliance |
| Single-action responses | >90% | One-thing mode adherence |
| Hyperfocus interruptions | <5% | Flow protection working |

### 9.3 Anti-Metrics (Things We DON'T Optimize)

- Daily active users (sporadic use is fine)
- Tasks completed (not a task manager)
- Session length (brevity is the goal)
- Notification click rate (fewer is better)

---

## 10. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| AI responses feel robotic | Users disengage | Medium | Heavy prompt engineering for warmth |
| Context capture misses state | Resumption fails | Medium | Multiple capture methods, user correction |
| RSD-safe language feels patronizing | Users feel talked down to | Medium | User-adjustable tone settings |
| Hyperfocus detection false positives | Misses urgent items | Low | User override, conservative detection |
| Users expect task manager | Disappointment | Medium | Clear positioning, onboarding |

---

## 11. Out of Scope

| Feature | Reason |
|---------|--------|
| Full task management | We're an assistant, not a todo app |
| Calendar replacement | Integrate with existing, don't replace |
| Team collaboration | Focus on individual ADHD support |
| Mobile app | Channel-native means existing apps |
| Voice interface (v1) | Text-first, voice in future version |

---

## 12. References

| Document | Location | Purpose |
|----------|----------|---------|
| ADHD Design Principles | `context/adhd_design_principles.md` | Full design philosophy |
| Technical Architecture | `goals/phase1_security.md` | Security implementation |
| Web Dashboard | `goals/phase7_dashboard.md` | Dashboard specification |
| Guided Installation | `goals/phase8_installation.md` | Setup wizard specification |
| Competitive Analysis | `context/openclaw_research.md` | Market context |
| Gap Analysis | `context/gap_analysis.md` | Feature comparison |
| System Handbook | `CLAUDE.md` | Operational guide |

---

*This PRD is a living document. Update as we learn from users.*
