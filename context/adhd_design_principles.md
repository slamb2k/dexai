# DexAI - Design Principles for Neuro-Divergent Users

> **Core Philosophy**: Most productivity tools fail ADHD users because they're built on a neurotypical assumption: that the user has consistent executive function available to *operate the system itself*. DexAI must be **zero-maintenance by default** — it should never become another abandoned system in the ADHD app graveyard. Every feature should work even if the user forgets the assistant exists for three days.

---

## Layer 1: Communication Design (Highest Priority)

### Adaptive Brevity with Recoverable Depth

The default output should be brutally short — one sentence, one action. But the user can always ask "why?" or "more" to expand. This respects both:
- Low-attention moments (need brevity)
- Hyperfocus moments (want depth)

### Tone Calibration Around Rejection Sensitivity (RSD)

**This is non-negotiable.** The assistant should NEVER:
- Use language that implies the user *should have* done something ("you still haven't...")
- Frame things as failures or missed deadlines
- Stack up overdue items in a guilt-inducing list

**Instead, reframe everything as forward-facing:**
- ❌ "You still haven't sent the invoice (3 days overdue)"
- ✅ "Ready to pick up the invoice thing when you are — want me to draft it now?"

The task still surfaces, but without shame. The emotional safety of the system directly determines whether the user will keep engaging with it or start avoiding it.

### "One Thing" Responses

When the user asks "what should I do?" — resist the urge to present options or prioritized lists.

ADHD decision fatigue means **a list of five things is actually zero things**.

The answer should be:
> "Send that email to Marcus. Here's a draft."

One thing. Pre-decided. With the friction already removed.

The user can reject it and ask for something else, but the default is a single actionable commitment.

---

## Layer 2: Notification Architecture (Critical)

### Time-Blindness-Aware Scheduling

Standard reminders ("meeting in 15 minutes") fail because they assume the user can accurately judge what fits in 15 minutes.

DexAI should understand **transition time** — the actual time it takes an ADHD brain to:
1. Disengage from the current thing
2. Context-switch
3. Arrive ready

**Example:** A 2pm meeting might need a nudge at 1:35:
> "Start wrapping up — you've got the design review at 2 and you'll want a few minutes to pull up the doc."

### Escalating Persistence Without Escalating Pressure

If something genuinely matters and the user hasn't responded:
- Re-surface it, but each re-surface feels like a fresh, friendly mention
- NOT an increasingly stern parent
- The *tone* stays constant; only the *frequency* changes
- Easy "snooze this for real, I know about it" escape valve

### Protect the Hyperfocus

When the user is in flow (detectable through interaction patterns):
- **Actively suppress** non-urgent notifications
- Queue everything
- Surface during a natural break

Interrupting productive hyperfocus is one of the most destructive things you can do to an ADHD workflow.

### Channel-Appropriate Interruption

Tiered notification system:
| Priority | Channel | Use Case |
|----------|---------|----------|
| Low | Silent inbox | FYI items, can wait |
| Medium | Gentle ambient nudge | Important but not urgent |
| High | Actual interruption | Time-critical only |

The user sets this once and forgets — DexAI learns what matters from behavior.

---

## Layer 3: External Working Memory (High Impact)

This is the most transformative feature for ADHD users. AI assistants are uniquely positioned to deliver this.

### Context Capture on Every Switch

When the user gets pulled away (message, pivot, wandering off):
- Automatically snapshot where they were
- What file was open
- What the last action was
- What the likely next step would have been

When they return (20 minutes or 3 days later):
> "You were halfway through the API integration. You'd just finished the auth flow and were about to wire up the endpoints. Want me to pull up where you left off?"

**This is the killer feature.** ADHD working memory means context switches cost 20-45 minutes of re-orientation. Eliminating that cost is genuinely life-changing.

### Relationship and Commitment Tracking

ADHD users frequently damage relationships through *forgetting*, not lack of caring.

Track:
- Unanswered messages that are aging
- Promises made in conversation ("I'll send you that article")
- Recurring social obligations
- People the user hasn't contacted in a while

Surface gently, not as a guilt list:
> "Sarah sent that message 3 days ago — want to reply now? Here's a quick draft based on what she asked."

### "Where Did I Put That?" Resolution

ADHD users lose things constantly — files, links, notes, half-finished documents.

Function as an always-available search:
> "The spreadsheet you were working on Tuesday — it's in your Downloads folder, you renamed it to 'budget-v3-FINAL-actual.xlsx'."

---

## Layer 4: Task Decomposition Engine (High Impact)

### Automatic Breakdown of Ambiguous Tasks

"Do taxes" is not a task, it's a project — but ADHD brains write it as one line item, feel overwhelmed, and avoid it.

Automatically decompose:
> "First step for taxes: find your group certificate. It's probably in your email from your employer around July. Want me to search for it?"

**Key insight:** The decomposition itself requires executive function the user may not have. Do this *proactively*, not on request. Present only the current step, not the full breakdown (which itself becomes overwhelming).

### Friction Estimation and Reduction

For each task, assess: what's the *actual barrier* to starting?

Often it's not the task but a prerequisite:
- Needing a password
- Needing to find a document
- Needing to make a phone call (its own ADHD nightmare)

Pre-solve the friction:
> "Before you can submit the form, you'll need your ABN. It's [number]. Here's the form pre-filled."

### Energy Matching

Not all hours are equal. Learn energy patterns and suggest tasks accordingly:
- Deep-focus work → Peak hours
- Admin tasks → Lower-energy periods
- Nothing demanding → Post-lunch dips

Inferred from interaction patterns over time — never requires user to self-report (they won't remember to).

---

## Layer 5: Dopamine-Aware Motivation (Long-Term)

### Progress Visibility

ADHD brains are dopamine-seeking and respond to visible progress.

Maintain lightweight metrics:
- Tasks completed today
- Streaks (handled carefully — broken streak should never feel like failure)
- "Look how much you got done this week" summaries

**Offered, not pushed** — available when the user wants a boost, not creating pressure.

### Momentum Protection

When productive, actively support continuing:
> "You've knocked out three things in the last hour — want to keep the streak going? The Jenkins config would take about 15 minutes."

Exploit the ADHD tendency: once moving, stay moving.

### Novelty Injection

ADHD brains habituate quickly — why they abandon systems.

Subtly vary approach:
- Different phrasings
- Occasional unexpected encouragements
- Varied formats

Not gimmicky — just enough variation to prevent becoming invisible wallpaper.

---

## Anti-Patterns to ALWAYS Avoid

| ❌ Never Do This | Why It Fails |
|------------------|--------------|
| Require daily check-ins or reviews | User does it for a week, stops, feels guilty, avoids system |
| Display count of overdue items | Number only grows, creates anxiety and avoidance |
| Require user to categorize/tag/organize | They won't, then feel bad about the mess |
| Assume yesterday's system still works | Build graceful degradation — re-engagement should feel fresh |
| Present more than three choices | Two is better. One is best. |

---

## Implementation Priority

### Week 1 — Immediate Wins
- One-thing task surfacing
- Gentle notification tone
- Context capture on switches
- Basic "where was I?" recovery

### Month 1 — Foundation
- Task decomposition engine
- Relationship/commitment tracking
- Notification tiering
- Friction pre-solving

### Month 3 — Learning
- Energy pattern recognition
- Hyperfocus detection and protection
- Adaptive communication style
- Progress visualization

### Month 6+ — Compounding
- Predictive task surfacing (knowing needs before user asks)
- Deep pattern recognition across life domains
- Proactive life-admin automation
- System becomes genuinely invisible

---

## Success Metric

> **The ultimate measure of success isn't feature richness — it's whether the user is still using it six months later.**

That requires the system to be:
1. **Effortless to maintain**
2. **Emotionally safe to return to after absence**
3. **Genuinely reducing cognitive load rather than adding to it**

Every feature decision should be filtered through that lens.
