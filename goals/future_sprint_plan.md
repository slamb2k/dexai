# DexAI Future Sprint Plan

> **Generated:** 2026-02-13
> **Scope:** Post Tier-6 hardening, synthesized from PRD, gap analysis, framework review findings, test coverage audit, dashboard analysis, and memory/context documents.
> **Methodology:** 6 parallel research agents analyzed: goals manifest + PRD, git history (97 PRs), tools/codebase (200+ files), memory/context docs, test coverage (761 cases), and dashboard state.

---

## Executive Summary

DexAI has completed **15 of 17 planned phases** and a comprehensive **6-tier security hardening sprint** (174 findings addressed). The system is production-ready for beta deployment. This plan prioritizes the remaining work into **5 sprints** organized by impact and risk:

| Sprint | Theme | Duration | Risk Level |
|--------|-------|----------|------------|
| **S1** | Critical Fixes & Stability | 3-5 days | Blocking |
| **S2** | Test Coverage & Quality Gate | 5-7 days | High |
| **S3** | Observability Maturity (Level 2 → 3) | 5-7 days | Medium |
| **S4** | Phase 14 — Analytics & Insights | 7-10 days | Medium |
| **S5** | Phase 13 — Collaborative Features | 7-10 days | Low |

**Post-MVP (backlog):** SDK Phase 3-4, skill runtime system, mobile polish, dashboard UX, competitive gap closure.

---

## Sprint 1: Critical Fixes & Stability

**Goal:** Eliminate known bugs and security gaps before any beta exposure.
**Duration:** 3-5 days
**Priority:** BLOCKING — must complete before beta users

### 1.1 Security TODOs (HIGH)

| Item | Location | Issue | Fix |
|------|----------|-------|-----|
| **Encrypt OAuth tokens** | `tools/dashboard/backend/routes/oauth.py:173,198` | `access_token` stored in plaintext; TODO comment acknowledges it | Use `tools/security/vault.py` to encrypt before storage |
| **Authenticate chat route** | `tools/dashboard/backend/routes/chat.py:106` | `user_id = "anonymous"` hardcoded; TODO says "get from session" | Wire up session-based auth from `tools/security/session.py` |
| **Office connection tests** | `tools/office/onboarding.py:445,459` | IMAP test and provider API test are stubs | Implement connection validation or remove dead code paths |

### 1.2 Audit System Bugs (CRITICAL)

| Item | Location | Issue | Impact |
|------|----------|-------|--------|
| **Tool use events silently failing** | `tools/agent/hooks.py:729` → `audit.py:43-52` | Hook logs `event_type="tool_use"` but audit module doesn't recognize it as valid | **Zero visibility** into what tools Claude invokes |
| **Dashboard tool recording dead code** | `tools/agent/hooks.py:800-805` | Imports `record_tool_use` from dashboard DB — function doesn't exist | PostToolUse dashboard recording never runs |
| **Two incompatible audit databases** | `data/audit.db` vs `data/dashboard.db` | Different schemas, different field names | Cannot query "what happened at 3pm?" across both systems |

### 1.3 Missing MCP Tool Registration

| Item | Details |
|------|---------|
| 7 MCP tools not exposed to agent | `dexai_schedule_list`, `dexai_schedule_manage`, `dexai_suppressed_count`, `dexai_release_suppressed`, `dexai_get_linked_channels` + 2 others exist in code but aren't registered in the SDK server |

### 1.4 Office Token Refresh

| Item | Details |
|------|---------|
| No token refresh before API calls | OAuth tokens could expire mid-API-call. Vault + refresh token infrastructure exists but isn't wired into the office integration call path |

**Exit Criteria:**
- [x] All 5 TODOs in source code resolved
- [x] `tool_use` verified in audit VALID_TYPES (was already present post-Tier 6)
- [x] `record_tool_use()` implemented in database.py
- [x] 5 critical MCP tools registered (ADHD + skills); setup-only tools excluded per design
- [x] OAuth token refresh verified (was already wired in both providers)

---

## Sprint 2: Test Coverage & Quality Gate

**Goal:** Raise coverage from ~15% to 50%+ and enforce quality gates in CI.
**Duration:** 5-7 days
**Priority:** HIGH — enables confident iteration in later sprints

### 2.1 Critical Module Testing

| Module | Current | Target | Files | Estimated Effort |
|--------|---------|--------|-------|------------------|
| **Dashboard Backend** | 5% (1 test) | 60% | 20 route/service files | 12-16 hours |
| **Automation** | 0% | 70% | 8 files (scheduler, heartbeat, triggers) | 8-12 hours |
| **Office Integration** | 0% | 40% | 41 files (start with OAuth, inbox, calendar) | 12-16 hours |
| **Mobile/Push** | 0% | 40% | 18 files (queue, delivery, web push) | 8-12 hours |
| **Setup/CLI** | 0% | 30% | 4+ files | 4-6 hours |

### 2.2 Quality Gate Enforcement

| Action | Current State | Target |
|--------|---------------|--------|
| Coverage threshold | `fail_under = 0` | `fail_under = 40` (raise to 60 in S3) |
| mypy strictness | Non-blocking, `--ignore-missing-imports` | Blocking for new code; keep non-blocking for legacy |
| Pre-push hook | None | Local lint + test before push |

### 2.3 Test Infrastructure

| Action | Details |
|--------|---------|
| Create mock factories | Reusable mocks for Anthropic, Google, Microsoft, OpenRouter APIs |
| Add E2E test skeleton | Playwright tests for dashboard critical paths (login, chat, task flow) |
| Document test patterns | `TESTING.md` with async patterns, fixture usage, API mocking examples |

**Exit Criteria:**
- [ ] Coverage threshold at 40% and enforced in CI
- [ ] All 4 untested modules have at least basic test suites
- [ ] Dashboard backend routes have individual test files
- [ ] Pre-push hook catches lint + test failures locally
- [ ] `TESTING.md` exists with patterns and examples

---

## Sprint 3: Observability Maturity (Level 2 → Level 3)

**Goal:** Move from "what happened?" (reactive) to "what's happening now and why?" (proactive).
**Duration:** 5-7 days
**Priority:** MEDIUM — needed for production confidence

### 3.1 Correlation & Tracing

| Action | Details |
|--------|---------|
| **Trace ID threading** | Generate `trace_id` at request entry (channel adapter), propagate through hooks → audit → dashboard → tools |
| **Audit DB consolidation** | Merge `audit.db` + `dashboard.db` into single unified schema with migration |
| **Agent decision traces** | Log model selection reason, tool choice rationale, decomposition reasoning per turn |
| **User session timeline** | Correlate channel messages → agent turns → tool uses → audit events into queryable timeline |

### 3.2 Structured Logging Migration

| Action | Details |
|--------|---------|
| **structlog everywhere** | Replace remaining `print()` and `logging.info()` calls with `structlog` bound loggers |
| **JSON output in production** | Configure structlog for JSON rendering in Docker, human-readable in dev |
| **Log levels standardized** | Define what goes at DEBUG/INFO/WARNING/ERROR across all modules |

### 3.3 Alerting Pipeline

| Action | Details |
|--------|---------|
| **Error rate alerts** | Trigger notification when error rate exceeds threshold over 5-minute window |
| **Cost alerts** | Alert when daily/session cost approaches budget limit (existing budget tracking + new alert dispatch) |
| **Health degradation** | Alert when circuit breaker trips or external service fails repeatedly |
| **Delivery mechanism** | Use existing channel adapters (Telegram/Discord/Slack) for alert delivery to admin |

### 3.4 Metrics Enhancement

| Action | Details |
|--------|---------|
| **Tool execution latency** | Record p50/p95/p99 for each tool type |
| **Subagent effectiveness** | Track which subagents are invoked, how often their output is used |
| **Memory search quality** | Log query → result relevance scores for tuning |
| **Cost attribution** | Per-conversation and per-user cost breakdown (building on existing per-call tracking) |

**Exit Criteria:**
- [ ] Single unified audit database with migration from dual-DB state
- [ ] Trace IDs flow from channel message through entire pipeline
- [ ] Alerting sends notifications for error spikes and budget warnings
- [ ] Dashboard shows agent decision traces (why this model, why this tool)
- [ ] Structured JSON logs in production Docker containers

---

## Sprint 4: Phase 14 — Analytics & Insights

**Goal:** Give users visibility into their patterns without guilt — the "look how much you did" experience.
**Duration:** 7-10 days
**Priority:** MEDIUM — high UX impact, all dependencies met

**Dependencies:** Phase 6 (energy tracking) ✅, Phase 7 (dashboard) ✅

### 4.1 Backend: Analytics Engine

| Component | Details |
|-----------|---------|
| **Weekly digest generator** | Aggregate tasks completed, energy patterns, peak hours, streaks |
| **Monthly summary** | Trend comparisons (self-only, never peer comparison) |
| **Energy trend analysis** | Time-of-day × energy-level heatmap data |
| **Task completion patterns** | Which decomposition sizes work best, friction types encountered |
| **Streak tracking** | Days with at least one completed task (celebrate, don't guilt on breaks) |

### 4.2 Frontend: Analytics Dashboard

| Component | Details |
|-----------|---------|
| **Weekly summary card** | "This week: 23 tasks done, avg energy: medium, best day: Tuesday" |
| **Energy heatmap** | Time-of-day × day-of-week colored by energy level |
| **Task completion chart** | Bar chart by day with positive framing |
| **Effectiveness insights** | "You complete 40% more tasks in the morning" (actionable, not judgmental) |
| **PDF export** | Generate therapy-session-friendly reports (existing PDF tooling available) |

### 4.3 ADHD Design Constraints

| Constraint | Implementation |
|------------|----------------|
| **Self-only comparisons** | Never show averages, peer data, or rankings |
| **No guilt language** | "3 tasks completed" not "7 tasks remaining" |
| **Celebrate progress** | Highlight streaks and personal bests |
| **Limit data density** | Max 3 charts per view, progressive disclosure for details |
| **Actionable insights** | Every stat links to a suggestion ("Try scheduling deep work before 11am") |

**Exit Criteria:**
- [ ] Weekly digest generates automatically with RSD-safe language
- [ ] Analytics page with energy heatmap, task chart, and insights
- [ ] PDF export works for therapy session sharing
- [ ] No guilt-inducing language anywhere in analytics (verified by language filter)
- [ ] Self-only comparisons enforced (no peer/average data)

---

## Sprint 5: Phase 13 — Collaborative Features

**Goal:** Accountability partnerships and body doubling without social pressure.
**Duration:** 7-10 days
**Priority:** LOW — valuable but not blocking beta

**Dependencies:** Phase 2 (memory) ✅, Phase 12 (office) ✅

### 5.1 Accountability Partnerships

| Component | Details |
|-----------|---------|
| **Partner pairing** | Opt-in mutual accountability (invite code or channel-based) |
| **Shared task visibility** | See partner's active task (title only, not details) — togglable |
| **Celebration notifications** | "Your partner completed a task!" (positive only, never shame) |
| **Weekly progress digests** | Mutual summary: tasks done, streaks (no comparison framing) |

### 5.2 Virtual Body Doubling

| Component | Details |
|-----------|---------|
| **Presence indicator** | Show when partner is "working" (green dot, no details) |
| **Focus sessions** | Timed co-working blocks (25-min Pomodoro or custom) |
| **Session summary** | "You both worked for 2 hours today" (shared accomplishment) |
| **Channel integration** | Discord voice channels or Slack huddles for ambient co-working |

### 5.3 Safety & Privacy

| Constraint | Implementation |
|------------|----------------|
| **Fully opt-in** | Every sharing feature requires explicit consent |
| **Granular controls** | Share: nothing / task titles only / full tasks / energy level |
| **Easy exit** | One-click to pause or end partnership (no guilt) |
| **No leaderboards** | Never rank partners or show competitive metrics |
| **RSD protection** | Partner notifications are always positive or neutral |

**Exit Criteria:**
- [ ] Partner pairing works via invite code
- [ ] Shared task visibility with granular privacy controls
- [ ] Celebration notifications fire on task completion
- [ ] Body doubling presence indicator works on at least one channel
- [ ] All collaborative features are fully opt-in with easy exit

---

## Post-MVP Backlog (Prioritized)

Items below are tracked for future sprints after the 5 above. Ordered by estimated impact.

### Tier A: High Impact, Medium Effort

| Item | Source | Details |
|------|--------|---------|
| **Skill runtime system** | Extensibility review | Current skills are documentation-only; build runtime discovery, loader, and lifecycle (create → test → publish → deprecate) |
| **SDK Phase 3** | SDK alignment roadmap | Streaming input, structured output schemas for task decomposition, `.claude/commands/` for platform shortcuts |
| **Dashboard mobile responsiveness** | Dashboard analysis | Currently desktop-only; add responsive layouts for tablet/phone |
| **Audit log integrity** | Security review | HMAC chain or write-once verification for append-only guarantees (current audit allows DELETE + VACUUM) |

### Tier B: Medium Impact, Medium Effort

| Item | Source | Details |
|------|--------|---------|
| **SDK Phase 4 optimization** | SDK roadmap | Model selector tuning, hook performance monitoring, skill refinement recommendations |
| **Time-blindness awareness** | ADHD design principles | Notifications should warn earlier for upcoming events ("meeting in 15 min" → "start wrapping up") |
| **Hyperfocus protection** | ADHD design principles | Detect flow state and suppress non-critical notifications |
| **Dashboard light theme** | Dashboard analysis | Only dark theme exists; some users need light mode for accessibility |
| **Metrics export** | Dashboard analysis | Currently disabled; enable PDF/CSV export for metrics page |
| **Dashboard collapsible metrics** | Landing page redesign goal | Metrics row should collapse to pill summaries; no-scroll viewport |
| **Memory expiration cleanup** | Memory review | Schema exists for expiration but no background job runs cleanup |
| **Session transcript indexing** | Competitive gap analysis | OpenClaw indexes full transcripts; DexAI currently doesn't |

### Tier C: Lower Impact, Variable Effort

| Item | Source | Details |
|------|--------|---------|
| **WhatsApp channel** | Gap analysis, dashboard UI | "Coming Soon" in UI; largest user base but complex API |
| **Progress visualization boosts** | ADHD principles | "Look how much you did today" positive reinforcement moments |
| **Relationship check-in logic** | ADHD principles | Proactive "haven't talked to X in a while" suggestions |
| **Multi-agent memory isolation** | Memory review | Each subagent should have scoped memory access |
| **Custom dashboard layouts** | Dashboard analysis | User-arrangeable panels and widgets |
| **Wearable deep integration** | PRD future phases | Full Apple Watch experience, health data correlation |
| **Therapist/coach portal** | PRD future phases | Read-only view for mental health professionals |
| **Community features** | PRD future phases | Anonymous tips and ADHD strategy sharing |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Audit silent failures masking security events** | HIGH (confirmed bug) | HIGH | Sprint 1 fix: add `tool_use` to VALID_TYPES |
| **OAuth token exposure** | MEDIUM (plaintext storage confirmed) | HIGH | Sprint 1 fix: vault encryption |
| **Low test coverage hides regressions** | HIGH (15% coverage) | MEDIUM | Sprint 2: raise to 50%+ with quality gates |
| **Observability blind spots in production** | MEDIUM | HIGH | Sprint 3: trace IDs, alerting, unified audit |
| **Analytics guilt-triggering language** | LOW (language filter exists) | HIGH (RSD impact) | Sprint 4: double-verify with language filter on all analytics text |
| **Collaboration features causing social anxiety** | MEDIUM | HIGH (ADHD users) | Sprint 5: fully opt-in, no leaderboards, easy exit |

---

## Success Metrics

| Metric | Current | Post-S1 | Post-S3 | Post-S5 |
|--------|---------|---------|---------|---------|
| **Audit event capture rate** | ~0% (bug) | 100% | 100% | 100% |
| **Test coverage (file count)** | ~15% | ~15% | 50%+ | 55%+ |
| **Coverage threshold enforced** | 0% | 0% | 40% | 60% |
| **Observability maturity** | Level 2 | Level 2 | Level 3 | Level 3 |
| **Open security TODOs** | 5 | 0 | 0 | 0 |
| **Feature phases complete** | 15/17 | 15/17 | 15/17 | 17/17 |
| **Production readiness** | Beta-blocked | Beta-ready | Production-ready | Feature-complete |

---

## Dependencies Map

```
Sprint 1 (Critical Fixes)
    ↓
Sprint 2 (Test Coverage)  ←── needed for safe iteration
    ↓
Sprint 3 (Observability)  ←── needs unified audit from S1
    ↓                ↓
Sprint 4            Sprint 5
(Analytics)         (Collaboration)
  independent         independent
```

Sprints 4 and 5 are independent of each other and can be reordered or parallelized based on user demand signals.

---

## Appendix: Data Sources

| Source | Agent | Key Finding |
|--------|-------|-------------|
| `goals/manifest.md` + `goals/prd_dexai_v1.md` | Goals/PRD analysis | 15/17 phases complete; Phase 13 + 14 remaining |
| Git history (97 PRs, 12 days) | Git analysis | 6-tier hardening complete; zero open issues/PRs |
| `tools/manifest.md` + codebase scan | Tools analysis | 200+ Python files, 17 tool categories, production-ready |
| `context/gap_analysis.md` + memory | Context analysis | Competitive gaps, design principles partially implemented |
| `tests/` + `pyproject.toml` + CI config | Test analysis | 36 test files / 761 cases / ~15% coverage / 4 untested modules |
| Dashboard frontend + backend scan | Dashboard analysis | Feature-rich but mobile-unresponsive; some UX gaps |
