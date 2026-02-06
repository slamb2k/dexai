# Goal: Task Orchestration Patterns

## Purpose

Maximize efficiency when working on multi-step implementations by using the right task execution pattern.

## Core Patterns

### 1. Sequential Pattern

**When:** Each task depends on the previous task's output.

**Example:** Database migration workflow
```
Task 1: Backup database       ──▶  Task 2: Run migration  ──▶  Task 3: Verify schema
        (must complete)                (needs backup)              (needs migration)
```

**Implementation:**
```python
# Create tasks
TaskCreate(subject="Backup database", ...)        # ID: 1
TaskCreate(subject="Run migration", ...)          # ID: 2
TaskCreate(subject="Verify schema", ...)          # ID: 3

# Set dependencies
TaskUpdate(taskId="2", addBlockedBy=["1"])
TaskUpdate(taskId="3", addBlockedBy=["2"])

# Execute in order
TaskUpdate(taskId="1", status="in_progress")
# ... do work ...
TaskUpdate(taskId="1", status="completed")  # Unblocks task 2
```

---

### 2. Parallel Pattern

**When:** Tasks are independent and can run simultaneously.

**Example:** Building multiple tools that don't depend on each other
```
Task 1: Build audit.py      ┐
Task 2: Build sanitizer.py  ├──▶  All complete
Task 3: Build ratelimit.py  ┘
```

**Implementation:**
```python
# Create all tasks (no dependencies)
TaskCreate(subject="Build audit.py", ...)
TaskCreate(subject="Build sanitizer.py", ...)
TaskCreate(subject="Build ratelimit.py", ...)

# Work on them in any order (or use subagents for true parallelism)
# No blockedBy relationships needed
```

**With Subagents (True Parallel):**
```python
# Launch multiple Task agents simultaneously
Task(subagent_type="general-purpose", prompt="Build audit.py...", run_in_background=True)
Task(subagent_type="general-purpose", prompt="Build sanitizer.py...", run_in_background=True)
Task(subagent_type="general-purpose", prompt="Build ratelimit.py...", run_in_background=True)
```

---

### 3. Fan-Out Pattern

**When:** One high-level task decomposes into multiple parallel subtasks.

**Example:** "Implement Phase 1 Security" breaks into 6 tools
```
                    ┌─▶ audit.py
                    ├─▶ vault.py
Phase 1 Security ───┼─▶ sanitizer.py
                    ├─▶ ratelimit.py
                    ├─▶ session.py
                    └─▶ permissions.py
```

**Implementation:**
```python
# Create parent task
TaskCreate(subject="Implement Phase 1 Security", ...)  # ID: 1

# Create child tasks
TaskCreate(subject="Build audit.py", ...)              # ID: 2
TaskCreate(subject="Build vault.py", ...)              # ID: 3
TaskCreate(subject="Build sanitizer.py", ...)          # ID: 4
TaskCreate(subject="Build ratelimit.py", ...)          # ID: 5
TaskCreate(subject="Build session.py", ...)            # ID: 6
TaskCreate(subject="Build permissions.py", ...)        # ID: 7

# Parent blocks until all children complete
TaskUpdate(taskId="1", addBlockedBy=["2", "3", "4", "5", "6", "7"])

# Work on children (parallel)
# Parent auto-unblocks when all complete
```

---

### 4. Fan-In Pattern

**When:** Multiple independent tasks must complete before a final task.

**Example:** All channel adapters must be built before integration testing
```
Telegram adapter  ──┐
Discord adapter   ──┼──▶ Integration Testing
Slack adapter     ──┘
```

**Implementation:**
```python
# Create adapter tasks
TaskCreate(subject="Build Telegram adapter", ...)   # ID: 1
TaskCreate(subject="Build Discord adapter", ...)    # ID: 2
TaskCreate(subject="Build Slack adapter", ...)      # ID: 3

# Create final task that waits for all
TaskCreate(subject="Integration Testing", ...)      # ID: 4
TaskUpdate(taskId="4", addBlockedBy=["1", "2", "3"])

# Build adapters (parallel)
# Integration testing auto-unblocks when all complete
```

---

### 5. Pipeline Pattern

**When:** Work flows through stages, with parallelism within stages.

**Example:** Build → Test → Deploy pipeline
```
Stage 1 (Build):     Stage 2 (Test):      Stage 3 (Deploy):
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Build API   │──┐   │ Unit Tests  │──┐   │             │
├─────────────┤  ├──▶├─────────────┤  ├──▶│   Deploy    │
│ Build UI    │──┘   │ E2E Tests   │──┘   │             │
└─────────────┘      └─────────────┘      └─────────────┘
```

**Implementation:**
```python
# Stage 1: Build (parallel)
TaskCreate(subject="Build API", ...)        # ID: 1
TaskCreate(subject="Build UI", ...)         # ID: 2

# Stage 2: Test (parallel, blocked by Stage 1)
TaskCreate(subject="Unit Tests", ...)       # ID: 3
TaskCreate(subject="E2E Tests", ...)        # ID: 4
TaskUpdate(taskId="3", addBlockedBy=["1", "2"])
TaskUpdate(taskId="4", addBlockedBy=["1", "2"])

# Stage 3: Deploy (blocked by Stage 2)
TaskCreate(subject="Deploy", ...)           # ID: 5
TaskUpdate(taskId="5", addBlockedBy=["3", "4"])
```

---

## Decision Matrix

| Scenario | Pattern | Reason |
|----------|---------|--------|
| A needs B's output | Sequential | Data dependency |
| A and B share nothing | Parallel | No dependency |
| Big task → many small | Fan-out | Decomposition |
| Many results → one check | Fan-in | Aggregation |
| Build → Test → Ship | Pipeline | Stage gates |

---

## Best Practices

1. **Create tasks upfront** — Full visibility before work starts
2. **Set dependencies immediately** — Prevents race conditions
3. **Use `in_progress` status** — Shows spinner to user, communicates activity
4. **Verify before `completed`** — Run tests, check outputs
5. **Keep descriptions detailed** — Another agent might pick up the task
6. **Clean up stale tasks** — Delete or complete abandoned tasks

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| No tasks for big work | Lost progress if session ends | Always create tasks |
| All sequential | Slow, can't parallelize | Identify independent work |
| Missing `in_progress` | User thinks nothing happening | Always set before work |
| Completing without verify | Broken code marked done | Test first |
| Orphan tasks | Cluttered list | Clean up weekly |

---

## Integration with GOTCHA

| GOTCHA Layer | Task Role |
|--------------|-----------|
| Goals | High-level tasks match goal workflows |
| Orchestration | Task system IS the orchestrator |
| Tools | Each tool invocation can be a task |
| Context | Task descriptions provide context |
| Hardprompts | N/A |
| Args | Task behavior configured in args |

---

## Related Files

- `CLAUDE.md` — Section 10: Task System
- `args/tasks.yaml` — Task configuration
