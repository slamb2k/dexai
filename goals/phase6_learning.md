# Phase 6: Learning & Personalization

> **Objective**: Learn user patterns to provide intelligent assistance without requiring configuration or self-reporting.

---

## Rationale

ADHD users won't fill out preference surveys. They won't remember to log their energy levels. They won't maintain a routine tracking habit.

But their behavior tells a story:
- Response times indicate mental sharpness
- Message length correlates with engagement
- Active sessions reveal flow states
- Task completions map to productive periods

**This phase builds a learning layer that observes, infers, and suggests — never requiring explicit input.**

The system should become smarter over time, matching tasks to energy levels, surfacing work at optimal times, and recognizing patterns the user themselves may not notice.

---

## Dependencies

| Phase | Provides | Used By |
|-------|----------|---------|
| Phase 2 | Context capture, activity logs | Energy observation signals |
| Phase 4 | Flow detection, notification timing | Flow state integration |
| Phase 5 | Task engine, decomposition | Task-energy matching |

---

## Components

### 1. Energy Tracker (`tools/learning/energy_tracker.py`)

**Purpose**: Infer energy levels from observable activity patterns.

**Signals Tracked**:
| Signal | Measurement | Energy Correlation |
|--------|-------------|-------------------|
| Response time | Time between messages | Faster = higher energy |
| Message length | Character/word count | Longer = higher engagement |
| Active duration | Session length | Longer = flow state |
| Task completion | Tasks marked done | More = productive period |
| Error frequency | Mistakes, corrections | More = fatigue |

**Database Schema** (`data/learning.db`):
```sql
-- Individual observations
CREATE TABLE IF NOT EXISTS energy_observations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    observed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    hour INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    signals TEXT,  -- JSON: {response_time_ms, message_length, active_duration_s, tasks_completed}
    inferred_energy TEXT CHECK(inferred_energy IN ('low', 'medium', 'high', 'peak')),
    confidence REAL DEFAULT 0.5
);

-- Aggregated profiles (updated periodically)
CREATE TABLE IF NOT EXISTS energy_profiles (
    user_id TEXT NOT NULL,
    day_of_week INTEGER NOT NULL,  -- 0=Monday, 6=Sunday
    hour INTEGER NOT NULL,         -- 0-23
    avg_energy_score REAL DEFAULT 0.5,  -- 0.0-1.0
    sample_count INTEGER DEFAULT 0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, day_of_week, hour)
);

-- Derived peak hours per day
CREATE TABLE IF NOT EXISTS peak_hours (
    user_id TEXT PRIMARY KEY,
    monday TEXT,     -- JSON array: [9, 10, 11]
    tuesday TEXT,
    wednesday TEXT,
    thursday TEXT,
    friday TEXT,
    saturday TEXT,
    sunday TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**CLI Interface**:
```bash
# Record an observation
python tools/learning/energy_tracker.py --action record --user alice \
    --signals '{"response_time_ms": 1200, "message_length": 45}'

# Get current energy estimate
python tools/learning/energy_tracker.py --action current --user alice

# Get full energy profile (all hours)
python tools/learning/energy_tracker.py --action profile --user alice

# Get peak hours for a day
python tools/learning/energy_tracker.py --action peak-hours --user alice --day monday

# Rebuild profiles from observations
python tools/learning/energy_tracker.py --action rebuild --user alice
```

**Key Design Decisions**:
- Minimum 10 samples before generating a profile (configurable)
- Confidence score reflects sample size and consistency
- Graceful degradation: returns "insufficient data" rather than guessing
- Observations auto-timestamped, never requires manual entry

---

### 2. Pattern Analyzer (`tools/learning/pattern_analyzer.py`)

**Purpose**: Detect recurring behavioral patterns from activity history.

**Pattern Types**:
| Type | Description | Example |
|------|-------------|---------|
| `daily_routine` | Same-time activities | "User checks messages at 9am" |
| `weekly_cycle` | Day-of-week patterns | "Mondays are meeting-heavy" |
| `avoidance` | Tasks consistently postponed | "Invoice tasks always pushed" |
| `productive_burst` | Clusters of completions | "3pm-5pm completion spike" |
| `context_switch` | Frequent topic changes | "Can't focus on one thing after 4pm" |

**Database Schema** (added to `learning.db`):
```sql
CREATE TABLE IF NOT EXISTS behavior_patterns (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    pattern_data TEXT NOT NULL,  -- JSON describing the pattern
    confidence REAL DEFAULT 0.5,
    sample_count INTEGER DEFAULT 0,
    first_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_observed DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_patterns_user ON behavior_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON behavior_patterns(user_id, pattern_type);
```

**CLI Interface**:
```bash
# Analyze all patterns for user
python tools/learning/pattern_analyzer.py --action analyze --user alice

# Get detected habits
python tools/learning/pattern_analyzer.py --action habits --user alice

# Get avoidance patterns (important for ADHD)
python tools/learning/pattern_analyzer.py --action avoidance --user alice

# Get weekly overview
python tools/learning/pattern_analyzer.py --action weekly --user alice

# Force pattern re-detection
python tools/learning/pattern_analyzer.py --action detect --user alice --since 30d
```

**Avoidance Detection (ADHD Critical)**:
- Track tasks that are repeatedly:
  - Snoozed
  - Pushed to "tomorrow"
  - Started but not completed
  - Never opened despite reminders
- Flag these patterns gently — information, not judgment
- Use for friction analysis: "What's blocking this?"

---

### 3. Task Matcher (`tools/learning/task_matcher.py`)

**Purpose**: Match tasks to optimal execution times based on energy and patterns.

**Core Functions**:

1. **Best Time for Task**: Given a task, when should it be done?
   - Maps task type to required energy level
   - Finds slots in user's energy profile that match
   - Considers existing commitments/calendar
   - Returns ranked time suggestions

2. **Best Task for Now**: Given current time, what should user work on?
   - Gets current energy estimate
   - Filters task list by energy match
   - Considers:
     - Due dates (without guilt framing)
     - Momentum (similar tasks if in flow)
     - Avoidance patterns (gently surface blocked tasks)
   - Returns single best suggestion (ADHD-friendly)

3. **Task Suggestions**: Proactive recommendations
   - "You have high energy right now — want to tackle the API design?"
   - "Low energy period — good time for email triage"

**Task Energy Requirements** (configurable in args):
```yaml
task_energy_requirements:
  creative: "peak"        # Writing, design, strategy
  problem_solving: "high" # Debugging, analysis
  writing: "medium"       # Documentation, emails
  admin: "low"            # Filing, organizing
  organizing: "low"       # Cleanup, sorting
  communication: "medium" # Calls, meetings
  learning: "high"        # New concepts, tutorials
```

**CLI Interface**:
```bash
# Best time for a specific task
python tools/learning/task_matcher.py --action best-time --user alice \
    --task "Write project proposal" --task-type creative

# Best task for right now
python tools/learning/task_matcher.py --action best-task --user alice

# Get suggestions based on current state
python tools/learning/task_matcher.py --action suggest --user alice --count 3

# Check if now is good for a task type
python tools/learning/task_matcher.py --action check --user alice --task-type creative
```

---

## Configuration (`args/learning.yaml`)

```yaml
learning:
  # Energy tracking configuration
  energy_tracking:
    enabled: true
    min_samples_for_pattern: 10
    confidence_threshold: 0.6
    decay_factor: 0.95  # Older observations matter slightly less

    # Signal weights for energy inference
    signals:
      response_time_weight: 0.3    # Faster responses = higher energy
      message_length_weight: 0.2   # Longer messages = more engaged
      active_duration_weight: 0.3  # Longer sessions = in flow
      task_completion_weight: 0.2  # Completing tasks = productive

    # Energy level thresholds (0.0 - 1.0 scale)
    thresholds:
      peak: 0.8    # Top 20% of user's range
      high: 0.6    # Above average
      medium: 0.4  # Average
      low: 0.0     # Below average

    # Response time benchmarks (ms)
    response_time_benchmarks:
      fast: 2000     # Under 2s = high energy signal
      normal: 5000   # 2-5s = normal
      slow: 10000    # Over 10s = low energy signal

  # Pattern detection configuration
  pattern_detection:
    enabled: true
    min_occurrences: 3          # Need 3+ instances to call it a pattern
    lookback_days: 30           # How far back to analyze
    avoidance_threshold: 3      # 3+ postponements = avoidance pattern
    routine_time_tolerance: 30  # Minutes variance for "same time"

  # Task matching configuration
  task_matching:
    enabled: true
    match_energy_to_task: true
    avoid_high_demand_in_low_energy: true
    suggest_easier_when_tired: true

    # Default task type -> energy requirement mapping
    task_energy_requirements:
      creative: "peak"
      problem_solving: "high"
      writing: "medium"
      admin: "low"
      organizing: "low"
      communication: "medium"
      learning: "high"
      review: "medium"

    # Fallback when not enough data
    fallback_behavior: "suggest_any"  # or "wait_for_data"
```

---

## Integration Points

### With Phase 2 (Working Memory)
- Context capture feeds activity signals to energy tracker
- Commitment tracking provides task completion data

### With Phase 4 (Smart Notifications)
- Flow detector provides real-time flow state
- Transition calculator uses energy for timing

### With Phase 5 (Task Engine)
- Task decomposition requests energy-appropriate subtasks
- Friction solver uses avoidance patterns

---

## ADHD-Specific Considerations

### No Self-Reporting
Users will not:
- Fill out daily energy logs
- Rate their mood
- Manually categorize tasks

**Everything must be inferred from behavior.**

### Graceful Degradation
When not enough data:
- Don't guess
- Don't show empty charts
- Say "I'm still learning your patterns" (no guilt)
- Provide general suggestions

### Avoidance is Information, Not Failure
When detecting avoidance patterns:
- Frame as curiosity: "I notice X keeps getting pushed..."
- Ask about friction: "Is something making this harder to start?"
- Offer help: "Want me to break this into smaller pieces?"

### Energy Levels Aren't Moral
- "Low energy" is not laziness
- "Peak hours" aren't about grinding harder
- Frame as optimization: "Match work to your rhythms"

---

## Verification Checklist

### Energy Tracking
- [ ] Energy observations recorded from activity signals
- [ ] Hourly profiles built per day of week
- [ ] Peak hours derived without user input
- [ ] Confidence scores reflect data quality
- [ ] Graceful response when data insufficient

### Pattern Analysis
- [ ] Daily routines detected from timestamps
- [ ] Weekly cycles identified
- [ ] Avoidance patterns flagged (3+ postponements)
- [ ] Patterns updated as new data arrives
- [ ] Old patterns decay when no longer observed

### Task Matching
- [ ] Tasks suggested based on current energy
- [ ] Best times suggested for task types
- [ ] Single best suggestion (not overwhelming lists)
- [ ] Respects task energy requirements
- [ ] Fallback behavior when data insufficient

### Integration
- [ ] Activity from channels feeds energy tracker
- [ ] Task completions update patterns
- [ ] Notifications respect learned preferences
- [ ] All outputs JSON-formatted for tooling

### ADHD Safety
- [ ] No self-reporting required
- [ ] No guilt-inducing language
- [ ] Avoidance framed as friction problem
- [ ] "Insufficient data" over bad guesses

---

## Testing Scenarios

### Scenario 1: Cold Start
New user with no history:
- System acknowledges it's learning
- Provides general task suggestions
- Starts building profile from first interactions

### Scenario 2: Pattern Emergence
After 2 weeks of use:
- Energy profile shows clear peaks
- "You're usually sharpest around 10am"
- Creative tasks suggested during peaks

### Scenario 3: Avoidance Detection
User keeps pushing off taxes:
- System notices 5 postponements
- "I notice taxes keeps getting pushed — want me to find the smallest first step?"
- No "you still haven't done..."

### Scenario 4: Energy Mismatch Prevention
User starts creative work at 4pm (their low period):
- "This might be easier tomorrow morning when you're usually sharper"
- Offers alternative: "Or I can break it into smaller pieces for now"

---

## Files to Create

| File | Purpose |
|------|---------|
| `tools/learning/__init__.py` | Package init with path constants |
| `tools/learning/energy_tracker.py` | Energy inference from activity |
| `tools/learning/pattern_analyzer.py` | Behavior pattern detection |
| `tools/learning/task_matcher.py` | Task-energy matching |
| `args/learning.yaml` | Configuration defaults |

---

## Success Metrics

1. **Energy Accuracy**: Suggested energy level matches user's self-reported state (when asked) >70% of time
2. **Pattern Detection**: System identifies patterns user confirms exist
3. **Task Matching**: Users report suggestions feel appropriate to their state
4. **Adoption**: Features remain in use after 30 days (no abandonment)

---

*Phase 6 is about building an assistant that understands the user better over time — without asking them to do anything.*
