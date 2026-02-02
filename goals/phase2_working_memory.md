# Goal: Phase 2 External Working Memory

## Objective
Build the external working memory system for DexAI, enabling ADHD users to recover context after interruptions and track commitments made in conversations.

## Rationale

> **This is the killer feature for ADHD users.**

Working memory deficits mean context switches cost 20-45 minutes of re-orientation. When an ADHD user gets pulled away (a message, a phone call, wandering off), they lose:
- What they were working on
- What the next step was
- What they promised to do

DexAI must function as an external working memory, automatically capturing context and providing "you were here..." resumption when the user returns.

From `context/adhd_design_principles.md`:
> "Context Capture on Every Switch... When they return (20 minutes or 3 days later): 'You were halfway through the API integration. You'd just finished the auth flow and were about to wire up the endpoints. Want me to pull up where you left off?'"

## Dependencies
- Phase 0 (Memory System) - uses context.db for storage
- Phase 1 (Channels) - captures context from channel interactions

---

## Components to Build

### 1. Context Capture (`tools/memory/context_capture.py`)

**Purpose:** Auto-snapshot user context when switches occur.

**Features:**
- Capture current state (active file, last action, next step, channel)
- Support triggers: 'switch', 'timeout', 'manual'
- Store snapshots in context.db
- List recent snapshots with filtering
- Retrieve specific snapshot by ID

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS context_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    captured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    trigger TEXT CHECK(trigger IN ('switch', 'timeout', 'manual')),
    state TEXT,  -- JSON: {active_file, last_action, next_step, channel, metadata}
    summary TEXT,
    expires_at DATETIME  -- Optional TTL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_user ON context_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON context_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_captured ON context_snapshots(user_id, captured_at DESC);
```

**CLI:**
```bash
# Capture context
python tools/memory/context_capture.py --action capture --user alice \
    --trigger switch \
    --active-file "/path/to/file.py" \
    --last-action "Wrote the auth middleware" \
    --next-step "Wire up the endpoints" \
    --channel discord

# List recent snapshots
python tools/memory/context_capture.py --action list --user alice --limit 10

# Get specific snapshot
python tools/memory/context_capture.py --action get --id "snap_abc123"

# Delete old snapshots (cleanup)
python tools/memory/context_capture.py --action cleanup --older-than "7d"
```

**Output Format:**
```json
{
    "success": true,
    "data": {
        "id": "snap_1706886400_alice",
        "user_id": "alice",
        "captured_at": "2024-02-02T12:00:00",
        "trigger": "switch",
        "state": {
            "active_file": "/home/user/project/auth.py",
            "last_action": "Wrote the auth middleware",
            "next_step": "Wire up the endpoints",
            "channel": "discord",
            "metadata": {}
        },
        "summary": null
    }
}
```

---

### 2. Context Resume (`tools/memory/context_resume.py`)

**Purpose:** Generate "you were here..." prompts when user returns.

**Features:**
- Fetch most recent context for user
- Generate human-friendly resumption prompt using LLM
- Return suggested next action
- Handle stale contexts gracefully (>168h old by default)
- Support ADHD-friendly tone (no guilt, forward-facing)

**CLI:**
```bash
# Generate resumption prompt for user
python tools/memory/context_resume.py --action resume --user alice

# Resume with specific snapshot
python tools/memory/context_resume.py --action resume --user alice --snapshot-id "snap_abc123"

# Just fetch context without generating prompt
python tools/memory/context_resume.py --action fetch --user alice
```

**Output Format:**
```json
{
    "success": true,
    "data": {
        "snapshot_id": "snap_1706886400_alice",
        "age_minutes": 45,
        "resumption_prompt": "You were working on the auth flow in auth.py. You'd just finished writing the middleware and were about to wire up the endpoints. Ready to pick that up?",
        "suggested_action": "Open /home/user/project/auth.py and add the endpoint routes",
        "context": {
            "active_file": "/home/user/project/auth.py",
            "last_action": "Wrote the auth middleware",
            "next_step": "Wire up the endpoints"
        }
    }
}
```

**ADHD Design Notes:**
- Never say "you still haven't..." or "you left this..."
- Always forward-facing: "Ready to pick up..." not "You abandoned..."
- If context is stale, don't guilt — just ask if still relevant
- Single action suggestion, not a list

---

### 3. Commitments Tracker (`tools/memory/commitments.py`)

**Purpose:** Track promises made in conversations so nothing falls through the cracks.

**Features:**
- Extract and store commitments from messages
- Track commitment lifecycle: active -> completed/cancelled
- Filter by status, user, target person
- Support due dates and reminders
- ADHD-friendly surfacing (not guilt lists)

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS commitments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    source_message_id TEXT,
    source_channel TEXT,
    target_person TEXT,
    due_date DATETIME,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    reminder_sent INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_commitments_user ON commitments(user_id);
CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
CREATE INDEX IF NOT EXISTS idx_commitments_user_status ON commitments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_commitments_due ON commitments(due_date);
CREATE INDEX IF NOT EXISTS idx_commitments_target ON commitments(target_person);
```

**CLI:**
```bash
# Add a commitment
python tools/memory/commitments.py --action add --user alice \
    --content "Send Sarah the API docs" \
    --target-person "Sarah" \
    --due-date "2024-02-05" \
    --source-channel "discord"

# List active commitments
python tools/memory/commitments.py --action list --user alice --status active

# Complete a commitment
python tools/memory/commitments.py --action complete --id "comm_abc123"

# Cancel a commitment
python tools/memory/commitments.py --action cancel --id "comm_abc123" --notes "Sarah found them herself"

# Get commitments due soon
python tools/memory/commitments.py --action due-soon --user alice --hours 24

# Extract commitments from text (uses LLM)
python tools/memory/commitments.py --action extract --user alice \
    --text "I'll send you the docs tomorrow and review the PR by Friday"
```

**Output Format:**
```json
{
    "success": true,
    "data": {
        "id": "comm_1706886400_alice",
        "user_id": "alice",
        "content": "Send Sarah the API docs",
        "target_person": "Sarah",
        "due_date": "2024-02-05T00:00:00",
        "status": "active",
        "created_at": "2024-02-02T12:00:00",
        "age_days": 0
    }
}
```

**ADHD Design Notes:**
- Surface commitments as opportunities, not obligations
- "Sarah's waiting on those docs — want to send them now?" (helpful)
- NOT "You still haven't sent Sarah the docs (3 days overdue)" (guilt-inducing)
- Group by target person when displaying (relationship context)

---

## Implementation Order

1. **Context Capture** — Foundation for resumption, captures raw state
2. **Context Resume** — Uses capture data to generate friendly prompts
3. **Commitments Tracker** — Independent but uses same database

---

## Configuration

### `args/working_memory.yaml`
```yaml
working_memory:
  auto_capture:
    enabled: true
    idle_timeout_seconds: 300      # Capture after 5 min idle
    min_context_age_seconds: 60    # Don't capture too frequently

  resumption:
    include_recent_commits: true   # Show recent commitments in resume
    max_context_age_hours: 168     # 7 days - older contexts are "stale"
    stale_context_message: "This is from a while ago - still relevant?"

  commitments:
    auto_extract: true             # Parse messages for promises
    reminder_after_hours: 24       # Gentle reminder timing
    max_age_days: 30               # Archive old unfulfilled commitments

  cleanup:
    snapshot_retention_days: 7     # Delete old snapshots after this
    run_on_startup: true           # Auto-cleanup on daemon start
```

---

## Hardprompts

### `hardprompts/memory/resumption_prompt.md`
LLM template for generating ADHD-friendly "you were here" prompts from raw context.

### `hardprompts/memory/commitment_detection.md`
LLM template for extracting commitments from conversation text.

---

## Verification Checklist

- [ ] `context_capture.py --action capture` creates snapshot
- [ ] `context_capture.py --action list` returns user's snapshots
- [ ] `context_capture.py --action get` retrieves specific snapshot
- [ ] `context_capture.py --action cleanup` removes old snapshots
- [ ] `context_resume.py --action resume` generates friendly prompt
- [ ] `context_resume.py` handles stale contexts gracefully
- [ ] `context_resume.py` uses ADHD-friendly tone (no guilt)
- [ ] `commitments.py --action add` creates commitment
- [ ] `commitments.py --action list` filters by status
- [ ] `commitments.py --action complete` updates status
- [ ] `commitments.py --action due-soon` finds upcoming commitments
- [ ] `commitments.py --action extract` parses text for promises
- [ ] All tools have `--help` documentation
- [ ] All tools return JSON output with success/error format
- [ ] Database tables have appropriate indexes
- [ ] Config in args/working_memory.yaml is loaded by tools

---

## Integration Points

- **Channels** (Phase 1): Context capture triggers on channel message activity
- **Notifications** (Phase 4): Commitment reminders sent via notification system
- **Task Engine** (Phase 5): Commitments can become tasks when decomposed

---

## Success Criteria

> "The ultimate measure is whether the user can close their laptop, come back 3 days later, and DexAI helps them pick up exactly where they left off in under 30 seconds."

1. Context capture happens automatically (zero user effort)
2. Resumption prompts are genuinely helpful (tested with ADHD users)
3. Commitments surface without creating anxiety
4. System works even if user forgets it exists for days

---

## Output

When complete, update:
- `tools/manifest.md` with new Working Memory tools section
- `goals/manifest.md` to mark Phase 2 as complete
