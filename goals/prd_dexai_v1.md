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
| 1.1 | 2026-02-02 | Product Team | All Phases 0-8 marked complete with tool references |

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

| Phase | Focus | Status | Key Deliverable |
|-------|-------|--------|-----------------|
| 0 | Foundation | ✅ Complete | Security + Memory |
| 1 | Channels | ✅ Complete | Multi-platform messaging |
| 2 | Working Memory | ✅ Complete | Context capture + resumption |
| 3 | Communication | ✅ Complete | RSD-safe responses, one-thing mode |
| 4 | Notifications | ✅ Complete | Time-blind-aware, hyperfocus protection |
| 5 | Task Engine | ✅ Complete | Decomposition, friction-solving |
| 6 | Learning | ✅ Complete | Energy patterns, personalization |
| 7 | Dashboard | ✅ Complete | Web-based management interface |
| 8 | Installation | ✅ Complete | Guided setup wizard (web + TUI) |
| 9 | CI/CD & Testing | 🔜 In Progress | GitHub Actions, pytest, Vitest |

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

### 6.3 Phase 1: Channels (COMPLETE)

**Status:** ✅ Done

**Objective:** Meet users where they are — messaging apps they already use.

| Feature | Tool | Status |
|---------|------|--------|
| Unified message model | `tools/channels/models.py` | ✅ |
| Message inbox | `tools/channels/inbox.py` | ✅ |
| Channel router | `tools/channels/router.py` | ✅ |
| Telegram adapter | `tools/channels/telegram.py` | ✅ |
| Discord adapter | `tools/channels/discord.py` | ✅ |
| Slack adapter | `tools/channels/slack.py` | ✅ |
| WebSocket gateway | `tools/channels/gateway.py` | ✅ |

### 6.4 Phase 2: External Working Memory (COMPLETE)

**Status:** ✅ Done

**Objective:** Eliminate context-switch cost — the killer feature for ADHD users.

| Feature | Tool | Status |
|---------|------|--------|
| Context snapshot | `tools/memory/context_capture.py` | ✅ |
| Resumption prompt | `tools/memory/context_resume.py` | ✅ |
| Commitment tracker | `tools/memory/commitments.py` | ✅ |
| Hardprompts | `hardprompts/memory/*.md` | ✅ |
| Configuration | `args/working_memory.yaml` | ✅ |

### 6.5 Phase 3: ADHD Communication Mode (COMPLETE)

**Status:** ✅ Done

**Objective:** Tone and style that's safe for rejection-sensitive brains.

| Feature | Tool | Status |
|---------|------|--------|
| Brevity default | `tools/adhd/response_formatter.py` | ✅ |
| RSD-safe language | `tools/adhd/language_filter.py` | ✅ |
| One-thing mode | `tools/adhd/response_formatter.py` | ✅ |
| Hardprompts | `hardprompts/adhd/*.md` | ✅ |
| Configuration | `args/adhd_mode.yaml` | ✅ |

### 6.6 Phase 4: Smart Notifications (COMPLETE)

**Status:** ✅ Done

**Objective:** Notifications that work with ADHD, not against it.

| Feature | Tool | Status |
|---------|------|--------|
| Transition time | `tools/automation/transition_calculator.py` | ✅ |
| Hyperfocus detection | `tools/automation/flow_detector.py` | ✅ |
| Interrupt suppression | `tools/automation/notify.py` (extended) | ✅ |
| Flow-aware queuing | `tools/automation/notify.py` | ✅ |
| Configuration | `args/smart_notifications.yaml` | ✅ |

### 6.7 Phase 5: Task Engine (COMPLETE)

**Status:** ✅ Done

**Objective:** Do the executive function work the user can't.

| Feature | Tool | Status |
|---------|------|--------|
| Auto-decomposition | `tools/tasks/decompose.py` | ✅ |
| Current step only | `tools/tasks/current_step.py` | ✅ |
| Friction detection | `tools/tasks/friction_solver.py` | ✅ |
| Task management | `tools/tasks/manager.py` | ✅ |
| Hardprompts | `hardprompts/tasks/*.md` | ✅ |
| Configuration | `args/task_engine.yaml` | ✅ |

### 6.8 Phase 6: Learning & Personalization (COMPLETE)

**Status:** ✅ Done

**Objective:** Get better at predicting user needs over time.

| Feature | Tool | Status |
|---------|------|--------|
| Energy patterns | `tools/learning/energy_tracker.py` | ✅ |
| Pattern analysis | `tools/learning/pattern_analyzer.py` | ✅ |
| Task matching | `tools/learning/task_matcher.py` | ✅ |
| Configuration | `args/learning.yaml` | ✅ |

### 6.9 Phase 7: Web Dashboard (COMPLETE)

**Status:** ✅ Done

**Objective:** Visual management interface for monitoring, configuring, and debugging DexAI.

> **Full specification:** `goals/phase7_dashboard.md`

| Feature | Tool | Status |
|---------|------|--------|
| FastAPI Backend | `tools/dashboard/backend/main.py` | ✅ |
| WebSocket Server | `tools/dashboard/backend/websocket.py` | ✅ |
| API Routes | `tools/dashboard/backend/routes/*.py` | ✅ |
| Next.js Frontend | `tools/dashboard/frontend/` | ✅ |
| Dex Avatar (9 states) | `frontend/components/dex-avatar.tsx` | ✅ |
| Activity Feed | `frontend/components/activity-feed.tsx` | ✅ |
| All Pages | `frontend/app/*/page.tsx` | ✅ |
| Configuration | `args/dashboard.yaml` | ✅ |

**Design Philosophy:**
- Dark, calm aesthetic (Modal.com-inspired)
- Black/blue color palette with subtle glows
- Immediate visual feedback reduces ADHD anxiety ("is it working?")
- Clean, uncluttered — information density without overwhelm

**Technology Stack:** Next.js 14, Tailwind CSS, shadcn/ui, Recharts, Socket.IO

### 6.10 Phase 8: Guided Installation (COMPLETE)

**Status:** ✅ Done

**Objective:** Zero-friction onboarding that gets users to first successful interaction in minutes.

> **Full specification:** `goals/phase8_installation.md`

| Feature | Tool | Status |
|---------|------|--------|
| Setup State Management | `tools/setup/wizard.py` | ✅ |
| TUI Wizard | `tools/setup/tui/main.py` | ✅ |
| Channel Validation | `tools/setup/wizard.py` | ✅ |
| Credential Storage | Via `tools/security/vault.py` | ✅ |
| Telegram Guide | `tools/setup/guides/telegram.md` | ✅ |
| Discord Guide | `tools/setup/guides/discord.md` | ✅ |
| Slack Guide | `tools/setup/guides/slack.md` | ✅ |
| Configuration | `args/setup.yaml` | ✅ |

**Design Philosophy:**
- Progressive disclosure — one thing at a time
- Smart defaults — configure later, not during setup
- Immediate feedback — test each step before continuing
- ADHD-friendly — no walls of text, clear progress indicators

**Technology Stack:** Textual (TUI), Next.js (web), existing channel adapters

### 6.11 Phase 9: CI/CD & Testing (IN PROGRESS)

**Status:** 🔜 In Progress

**Objective:** Ensure code quality and prevent regressions through automated testing and continuous integration.

> **Full specification:** `goals/phase9_ci_testing.md`

| Feature | Tool | Status |
|---------|------|--------|
| Python Project Config | `pyproject.toml` | 🔜 |
| GitHub Actions CI | `.github/workflows/ci.yml` | 🔜 |
| Pytest Infrastructure | `tests/conftest.py` | 🔜 |
| Security Tests | `tests/unit/security/*.py` | 🔜 |
| ADHD Tool Tests | `tests/unit/adhd/*.py` | 🔜 |
| Task Engine Tests | `tests/unit/tasks/*.py` | 🔜 |
| Memory Tests | `tests/unit/memory/*.py` | 🔜 |
| Frontend Tests | `frontend/__tests__/*.tsx` | 🔜 |

**Design Philosophy:**
- Test critical paths first (security, ADHD communication, task engine)
- Use fixtures for database isolation
- Parallel test execution where possible
- Coverage targets: >80% for critical modules

**Technology Stack:** pytest, ruff, mypy, Vitest, GitHub Actions

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

### 8.1 Implementation Status

```
2026
├── Feb 02: Phase 0 Complete (Security + Memory) ✅
├── Feb 02: Phase 1 Complete (Channels) ✅
├── Feb 02: Phase 2 Complete (External Working Memory) ✅
├── Feb 02: Phase 3 Complete (ADHD Communication Mode) ✅
├── Feb 02: Phase 4 Complete (Smart Notifications) ✅
├── Feb 02: Phase 5 Complete (Task Engine) ✅
├── Feb 02: Phase 6 Complete (Learning) ✅
├── Feb 02: Phase 7 Complete (Web Dashboard) ✅
├── Feb 02: Phase 8 Complete (Guided Installation) ✅
└── Feb 02: Phase 9 In Progress (CI/CD & Testing) 🔜

Phases 0-8 COMPLETE - Phase 9 adds continuous integration and test coverage
```

### 8.2 Next Steps

| Milestone | Status | Description |
|-----------|--------|-------------|
| Integration Testing | 🔜 Next | End-to-end testing of all components |
| Alpha Release | Pending | Deploy to founder testing environment |
| Beta Release | Pending | 10 ADHD beta users, feedback collection |
| GA | Pending | 6-month retention >50%, public release |

### 8.3 Release Criteria

| Milestone | Criteria |
|-----------|----------|
| Alpha | All tools functional, channel adapters tested, founder testing |
| Beta | All P0 features working end-to-end, 10 ADHD beta users |
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
