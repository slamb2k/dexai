# Phase 5: Task Decomposition Engine

> **Objective**: Break overwhelming tasks into actionable steps, identify hidden friction, and present ONLY the current step to prevent ADHD decision paralysis.

---

## Rationale

### The ADHD Task Problem

"Do taxes" is not a task, it's a project - but ADHD brains write it as one line item, feel overwhelmed, and avoid it.

**The decomposition itself requires executive function the user may not have.**

This phase builds the Task Engine that:
1. Auto-decomposes vague tasks into concrete steps
2. Identifies the ACTUAL barrier (often a prerequisite, not the task itself)
3. Presents ONLY the current step (not the whole breakdown - that's overwhelming)
4. Pre-solves friction where possible

### Key Insight: Friction is the Real Barrier

Often what blocks starting isn't the task but a prerequisite:
- Needing a password
- Needing to find a document
- Needing to make a phone call (its own ADHD nightmare)

The engine surfaces and pre-solves these hidden blockers.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Phase 2 (Working Memory) | Context capture, commitment tracking |
| Phase 3 (ADHD Communication) | RSD-safe language, one-thing responses |
| Phase 4 (Smart Notifications) | Flow-aware surfacing of tasks |
| `tools/security/permissions.py` | Access control for task operations |
| `tools/channels/router.py` | Message routing for task updates |

---

## Components

### 1. Task Manager (`tools/tasks/manager.py`)

**Purpose**: CRUD operations for tasks with parent/subtask relationships.

**Database Schema** (data/tasks.db):

```sql
-- Main tasks table
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    title TEXT,
    description TEXT,
    parent_task_id TEXT,
    current_step_id TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'abandoned')),
    energy_level TEXT CHECK(energy_level IN ('low', 'medium', 'high')),
    estimated_minutes INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    FOREIGN KEY(parent_task_id) REFERENCES tasks(id)
);

-- Individual steps within a task
CREATE TABLE task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    action_verb TEXT,  -- 'find', 'send', 'call', 'open', 'write'
    friction_notes TEXT,
    friction_solved INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'skipped')),
    completed_at DATETIME,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

-- Friction points that block progress
CREATE TABLE task_friction (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    step_id TEXT,
    friction_type TEXT,  -- 'missing_info', 'phone_call', 'decision', 'password', 'document'
    description TEXT,
    resolution TEXT,
    resolved INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**CLI Interface**:
```bash
# Create a new task
python tools/tasks/manager.py --action create --user alice --task "do taxes"

# List tasks for user
python tools/tasks/manager.py --action list --user alice --status pending

# Get task details
python tools/tasks/manager.py --action get --task-id abc123

# Update task
python tools/tasks/manager.py --action update --task-id abc123 --status in_progress

# Complete task
python tools/tasks/manager.py --action complete --task-id abc123

# Abandon task (without guilt!)
python tools/tasks/manager.py --action abandon --task-id abc123 --reason "no longer relevant"

# Complete a step
python tools/tasks/manager.py --action complete-step --step-id step123
```

**Return Format**:
```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "title": "File tax return",
    "status": "pending",
    "current_step": {
      "id": "step1",
      "description": "Find your group certificate in email",
      "friction_notes": "Search for 'payment summary' from employer"
    }
  }
}
```

---

### 2. Task Decomposer (`tools/tasks/decompose.py`)

**Purpose**: Break vague tasks into concrete, actionable steps.

**Behavior**:
1. Takes raw task input ("do taxes", "plan the party")
2. Uses LLM to decompose into 3-7 concrete steps
3. Each step starts with an action verb
4. Each step is completable in under 15 minutes
5. Returns ONLY the first step (not all steps)

**CLI Interface**:
```bash
# Decompose a task (shallow = first 2-3 steps only)
python tools/tasks/decompose.py --action decompose --task "do taxes" --user alice

# Full decomposition (all steps, for context)
python tools/tasks/decompose.py --action decompose --task "do taxes" --user alice --depth full

# Re-decompose (if first approach didn't work)
python tools/tasks/decompose.py --action redecompose --task-id abc123
```

**Return Format**:
```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "raw_input": "do taxes",
    "title": "File tax return",
    "total_steps": 5,
    "first_step": {
      "description": "Find your group certificate in your email",
      "action_verb": "find",
      "estimated_minutes": 5
    }
  }
}
```

**Rules for Decomposition**:
- Maximum 7 steps (more = project, not task)
- Each step has exactly one action
- Steps should be independent where possible
- No sub-sub-tasks (flatten to single level)
- Action verbs: find, send, call, open, write, review, submit, wait, book, check

---

### 3. Friction Solver (`tools/tasks/friction_solver.py`)

**Purpose**: Identify and pre-solve blockers before the user hits them.

**Friction Types**:
| Type | Description | Example |
|------|-------------|---------|
| `missing_info` | Need data before starting | "What's the login URL?" |
| `phone_call` | Dreaded phone task | "Call the dentist" |
| `decision` | Unmade choice blocking progress | "Which venue?" |
| `password` | Auth required | "Need MyGov password" |
| `document` | Need to find/create doc | "Where's the invoice?" |
| `appointment` | Need to schedule something | "Book a time with accountant" |

**CLI Interface**:
```bash
# Identify friction in a task
python tools/tasks/friction_solver.py --action identify --task-id abc123

# Identify friction in a specific step
python tools/tasks/friction_solver.py --action identify --step-id step123

# Mark friction as solved
python tools/tasks/friction_solver.py --action solve --friction-id f123 --resolution "Password saved in vault"

# List unresolved friction
python tools/tasks/friction_solver.py --action list --user alice --unresolved
```

**Return Format**:
```json
{
  "success": true,
  "data": {
    "friction_points": [
      {
        "id": "f123",
        "type": "password",
        "description": "Need MyGov login credentials",
        "suggested_resolution": "Check vault for saved credentials",
        "resolved": false
      }
    ]
  }
}
```

---

### 4. Current Step Provider (`tools/tasks/current_step.py`)

**Purpose**: Return ONLY the single next action. No lists. No future steps. Just ONE thing.

**Behavior**:
1. Finds the user's highest-priority pending task
2. Gets the current step (first incomplete step)
3. Includes pre-solved friction if relevant
4. Formats as actionable instruction
5. Never shows the full task breakdown

**CLI Interface**:
```bash
# Get current step for user (across all tasks)
python tools/tasks/current_step.py --action get --user alice

# Get current step for specific task
python tools/tasks/current_step.py --action get --user alice --task-id abc123

# Get step with energy consideration
python tools/tasks/current_step.py --action get --user alice --energy low
```

**Return Format**:
```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "task_title": "File tax return",
    "current_step": {
      "id": "step1",
      "description": "Find your group certificate",
      "action_verb": "find",
      "friction_pre_solved": "Search your email for 'payment summary' from [employer name]"
    },
    "formatted": "Find your group certificate - search your email for 'payment summary' from Acme Corp."
  }
}
```

---

## Configuration

**File**: `args/task_engine.yaml`

```yaml
task_engine:
  decomposition:
    auto_decompose: true
    max_steps: 7  # More than 7 = project, not task
    depth_default: "shallow"  # Only next 2-3 steps
    llm_model: "claude-3-haiku-20240307"  # Fast model for decomposition

  friction:
    auto_identify: true
    common_types:
      - missing_info
      - phone_call
      - decision_needed
      - password_required
      - document_needed
      - appointment_required

  presentation:
    one_step_only: true  # Never show full breakdown by default
    show_friction: true
    actionable_verbs: true  # Start steps with action verbs

  energy_matching:
    enabled: true
    levels:
      low: ["admin", "filing", "organizing", "cleanup"]
      medium: ["writing", "reviewing", "planning", "email"]
      high: ["creating", "problem-solving", "learning", "calls"]

  priorities:
    default: "medium"
    decay_days: 7  # After 7 days, gently re-surface stale tasks
```

---

## Hardprompts

### `hardprompts/tasks/decomposition.md`

LLM template for breaking tasks into steps. Rules:
- Action verbs only (find, send, call, open, write, review, submit)
- Each step under 15 minutes
- Maximum 7 steps
- No nested subtasks
- Consider common friction points

### `hardprompts/tasks/friction_identification.md`

LLM template for identifying blockers. Focus:
- Prerequisites, not the task itself
- Hidden friction (passwords, documents, decisions)
- Phone call aversion
- Information gaps

---

## Permissions

Add to `tools/security/permissions.py`:

```python
# Task Engine permissions
"task:create",      # Create new tasks
"task:read",        # View task details
"task:update",      # Modify tasks
"task:delete",      # Remove tasks
"task:decompose",   # Use decomposition engine
"task:friction",    # Access friction solver
```

---

## Verification Checklist

### Core Functionality
- [ ] "Do taxes" input decomposes to first concrete step
- [ ] Only current step shown (not full breakdown)
- [ ] Friction identified and noted on relevant steps
- [ ] Completed steps tracked with timestamps
- [ ] Tasks can be abandoned without guilt messaging

### Database
- [ ] tasks.db created with all tables
- [ ] Indexes on user_id, status, task_id
- [ ] Foreign keys enforced
- [ ] Status transitions validated

### CLI
- [ ] All actions work via CLI
- [ ] JSON output format consistent
- [ ] Help text available (--help)
- [ ] Error handling returns proper JSON

### Integration
- [ ] Permissions added and enforced
- [ ] Works with context capture (Phase 2)
- [ ] Uses RSD-safe language (Phase 3)
- [ ] Respects flow state (Phase 4)

### ADHD-Specific
- [ ] Never shows more than one step unprompted
- [ ] Language is forward-facing, never guilt-inducing
- [ ] Friction pre-solved where possible
- [ ] Energy matching suggests appropriate tasks

---

## Example Flow

**User says**: "I need to do my taxes"

**System**:
1. Creates task with raw_input "I need to do my taxes"
2. Decomposes into steps (hidden from user):
   - Find group certificate
   - Gather deduction receipts
   - Log into MyGov
   - Open ATO myTax
   - Enter income details
   - Enter deductions
   - Review and submit
3. Identifies friction:
   - Step 1: May be buried in email
   - Step 3: Needs password
4. Returns ONLY:
   > "First step: Find your group certificate. Try searching your email for 'payment summary' from your employer around July."

**User completes step 1**, says "done"

**System**:
1. Marks step 1 complete
2. Advances to step 2
3. Returns ONLY:
   > "Nice. Next: Gather your deduction receipts. Do you have a folder for these, or should we start fresh?"

This continues step-by-step. User never sees the full list. Never feels overwhelmed.

---

## Anti-Patterns to Avoid

| Don't | Why |
|-------|-----|
| Show full task breakdown upfront | Overwhelming, causes paralysis |
| Use "overdue" or "you still haven't" | RSD trigger, causes avoidance |
| Stack up incomplete tasks visibly | Growing number creates anxiety |
| Require user to categorize | Extra executive function load |
| Make abandonment feel like failure | Sometimes tasks become irrelevant |

---

*Phase 5 enables the core ADHD superpower: "What's the one thing I should do right now?"*
