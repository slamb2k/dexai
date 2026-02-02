# Phase 4: Smart Notifications

> **Objective**: Protect ADHD users from unnecessary interruptions through flow-state-aware notification management, time-blindness-compensating reminders, and intelligent suppression.

---

## Prerequisites

- **Phase 0** (Security + Memory): Audit logging for notification events
- **Phase 1** (Channels): Message routing and delivery infrastructure
- **Phase 3** (ADHD Comms): RSD-safe language patterns for notifications

---

## Rationale

Standard notification systems are hostile to ADHD brains:

1. **Flow State Destruction**: Interrupting hyperfocus costs 20-45 minutes of re-orientation. Every ping during productive flow is a catastrophic context switch.

2. **Time Blindness Ignorance**: "Meeting in 15 minutes" assumes the user can accurately judge what fits in 15 minutes. ADHD users need transition time accounting.

3. **Notification Fatigue**: Low-priority interruptions train the brain to ignore notifications entirely, causing important ones to be missed.

4. **Guilt Accumulation**: Stacking notifications create "notification debt" that becomes anxiety-inducing and avoidance-triggering.

**Solution**: A notification system that actively protects productivity by understanding flow state, accounting for transition time, and intelligently queueing non-urgent items.

---

## Components

### 1. Flow State Detector (`tools/automation/flow_detector.py`)

Detects when a user is in hyperfocus/flow state to protect productive time.

**Database Schema** (in `scheduler.db`):

```sql
CREATE TABLE IF NOT EXISTS activity_patterns (
    user_id TEXT NOT NULL,
    hour INTEGER,
    day_of_week INTEGER,
    message_count INTEGER DEFAULT 0,
    avg_response_time_seconds REAL,
    flow_score REAL DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, hour, day_of_week)
);

CREATE TABLE IF NOT EXISTS flow_overrides (
    user_id TEXT PRIMARY KEY,
    is_focusing INTEGER DEFAULT 0,
    until DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**CLI Interface**:

```bash
# Detect current flow state
python tools/automation/flow_detector.py --action detect --user alice
# Output: {"success": true, "in_flow": true, "score": 78, "source": "activity_pattern"}

# Get flow score only
python tools/automation/flow_detector.py --action score --user alice
# Output: {"success": true, "score": 78, "window_minutes": 15}

# Set manual focus mode
python tools/automation/flow_detector.py --action set-override --user alice --duration 60
# Output: {"success": true, "until": "2024-01-15T15:30:00", "message": "Focus mode enabled for 60 minutes"}

# Clear manual override
python tools/automation/flow_detector.py --action clear-override --user alice
# Output: {"success": true, "message": "Focus mode cleared"}

# Get current override status
python tools/automation/flow_detector.py --action get-override --user alice
# Output: {"success": true, "is_focusing": true, "until": "2024-01-15T15:30:00"}

# Record activity (called by message handlers)
python tools/automation/flow_detector.py --action record --user alice --response-time 5.2
# Output: {"success": true, "message": "Activity recorded"}

# Get historical patterns
python tools/automation/flow_detector.py --action patterns --user alice
# Output: {"success": true, "patterns": [...], "peak_hours": [10, 14, 21]}
```

**Flow Detection Logic**:

| Signal | Weight | Detection |
|--------|--------|-----------|
| Rapid response time (<30s) | High | Active engagement |
| High message density | High | Productive output |
| Manual override active | Absolute | User declared focus |
| Historical pattern match | Medium | This time slot usually productive |
| Long silence after burst | Low | May indicate deep work OR disengagement |

**Programmatic API**:

```python
from tools.automation.flow_detector import (
    detect_flow,
    get_flow_score,
    set_override,
    clear_override,
    record_activity
)

# Check if user is in flow
result = detect_flow(user_id="alice")
if result["in_flow"]:
    # Queue notification for later
    pass

# Record message activity
record_activity(user_id="alice", response_time_seconds=5.2)
```

---

### 2. Transition Time Calculator (`tools/automation/transition_calculator.py`)

Calculates ADHD-appropriate reminder times that account for:
- Task disengagement time
- Physical/mental context switching
- Buffer for unexpected delays

**Database Schema** (in `scheduler.db`):

```sql
CREATE TABLE IF NOT EXISTS transition_patterns (
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actual_transition_minutes REAL,
    on_time INTEGER,  -- 1 if arrived on time, 0 if late
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, event_type, recorded_at)
);

CREATE TABLE IF NOT EXISTS transition_defaults (
    user_id TEXT PRIMARY KEY,
    meeting_buffer INTEGER DEFAULT 25,
    deep_work_buffer INTEGER DEFAULT 30,
    admin_buffer INTEGER DEFAULT 15,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**CLI Interface**:

```bash
# Calculate reminder time for an event
python tools/automation/transition_calculator.py --action calculate --event-time "2024-01-15T14:00:00" --event-type meeting --user alice
# Output: {"success": true, "reminder_time": "2024-01-15T13:35:00", "buffer_minutes": 25, "reason": "Standard meeting buffer"}

# Calculate for deep work session ending
python tools/automation/transition_calculator.py --action calculate --event-time "2024-01-15T14:00:00" --event-type deep_work --user alice
# Output: {"success": true, "reminder_time": "2024-01-15T13:30:00", "buffer_minutes": 30, "reason": "Deep work requires longer disengagement"}

# Record actual transition (for learning)
python tools/automation/transition_calculator.py --action record --user alice --event-type meeting --actual-minutes 22 --on-time true
# Output: {"success": true, "message": "Transition recorded", "new_average": 23.5}

# Get user's transition patterns
python tools/automation/transition_calculator.py --action patterns --user alice
# Output: {"success": true, "patterns": {"meeting": 24.2, "deep_work": 28.5, "admin": 12.1}}

# Update user defaults
python tools/automation/transition_calculator.py --action set-defaults --user alice --meeting 30 --deep-work 35
# Output: {"success": true, "message": "Defaults updated"}
```

**Default Buffers** (ADHD-appropriate, not neurotypical):

| Event Type | Default Buffer | Rationale |
|------------|---------------|-----------|
| meeting | 25 minutes | Need time to disengage, context switch, arrive ready |
| deep_work | 30 minutes | Harder to disengage from hyperfocus |
| admin | 15 minutes | Lower cognitive load, easier to switch |
| social | 20 minutes | Emotional preparation needed |
| appointment | 35 minutes | Usually involves travel + uncertainty |

**Programmatic API**:

```python
from tools.automation.transition_calculator import (
    calculate_reminder_time,
    record_transition,
    get_patterns
)

# Get optimal reminder time
result = calculate_reminder_time(
    user_id="alice",
    event_time="2024-01-15T14:00:00",
    event_type="meeting"
)
print(result["reminder_time"])  # "2024-01-15T13:35:00"

# Learn from actual behavior
record_transition(
    user_id="alice",
    event_type="meeting",
    actual_minutes=22,
    on_time=True
)
```

---

### 3. Flow-Aware Notification Dispatch (extend `tools/automation/notify.py`)

Extend existing notify.py with flow state integration:

**New Database Tables** (in `scheduler.db`):

```sql
CREATE TABLE IF NOT EXISTS suppressed_notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    original_channel TEXT,
    suppression_reason TEXT,
    suppressed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    release_after DATETIME,
    released INTEGER DEFAULT 0,
    released_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_suppressed_user ON suppressed_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_suppressed_released ON suppressed_notifications(released);
```

**New CLI Actions**:

```bash
# Check if a notification should be suppressed
python tools/automation/notify.py --action check-flow --user alice --priority normal
# Output: {"success": true, "should_suppress": true, "reason": "User in flow state", "flow_score": 78}

# Send with flow awareness (suppresses if in flow)
python tools/automation/notify.py --action send --user alice --content "FYI: Report ready" --priority low --flow-aware
# Output: {"success": true, "suppressed": true, "queued_until": "flow_ends", "message": "Notification queued until flow ends"}

# Get suppressed notification count
python tools/automation/notify.py --action suppressed-count --user alice
# Output: {"success": true, "count": 3, "priorities": {"low": 2, "normal": 1}}

# Release suppressed notifications
python tools/automation/notify.py --action release-suppressed --user alice
# Output: {"success": true, "released": 3, "message": "3 notifications released"}

# Get queue of suppressed notifications
python tools/automation/notify.py --action list-suppressed --user alice
# Output: {"success": true, "notifications": [...], "count": 3}
```

**Suppression Logic**:

| Priority | During Light Flow | During Deep Flow | Manual Focus |
|----------|------------------|------------------|--------------|
| low | Suppress | Suppress | Suppress |
| normal | Allow | Suppress | Suppress |
| high | Allow | Allow | Suppress* |
| urgent | Allow | Allow | Allow |

*High priority during manual focus: notify but with gentle channel

**New Functions**:

```python
def should_suppress(user_id: str, priority: str) -> Dict[str, Any]:
    """Check if notification should be suppressed based on flow state."""

def queue_for_later(
    user_id: str,
    content: str,
    priority: str,
    channel: Optional[str] = None,
    release_after: Optional[str] = None
) -> str:
    """Queue notification for delivery after flow ends."""

def get_suppressed_count(user_id: str) -> Dict[str, Any]:
    """Get count of suppressed notifications by priority."""

def release_suppressed(user_id: str) -> Dict[str, Any]:
    """Release all suppressed notifications for user."""
```

---

### 4. Configuration (`args/smart_notifications.yaml`)

Central configuration for all smart notification behaviors:

```yaml
smart_notifications:
  flow_protection:
    enabled: true
    detection_window_minutes: 15
    min_activity_for_flow: 3  # messages in window
    flow_score_threshold: 60  # 0-100, above this = in flow
    suppress_low_priority: true
    suppress_medium_during_deep_flow: true
    deep_flow_threshold: 80

  transition_time:
    default_buffer_minutes: 25
    deep_work_buffer_minutes: 30
    admin_buffer_minutes: 15
    social_buffer_minutes: 20
    appointment_buffer_minutes: 35
    learn_from_patterns: true
    min_samples_for_learning: 5

  priority_tiers:
    low:
      channels: ["inbox"]  # Silent, check when ready
      suppress_during_flow: true
      aggregate: true
      aggregate_window_minutes: 30
    medium:
      channels: ["gentle_nudge"]
      suppress_during_deep_flow: true
      aggregate: false
    high:
      channels: ["interrupt"]
      suppress_during_flow: false
      use_gentle_during_focus: true  # Downgrade channel during manual focus
    urgent:
      channels: ["interrupt", "fallback_sms"]
      suppress_during_flow: false
      always_deliver: true

  active_hours:
    enabled: true
    start: "09:00"
    end: "22:00"
    timezone: "local"
    urgent_ignores_hours: true

  batch_delivery:
    enabled: true
    natural_break_detection: true
    max_queue_time_minutes: 120
    batch_summary_format: "digest"  # or "sequential"
```

---

## Integration Points

### With Channels Router (`tools/channels/router.py`)

The router should check flow state before delivery:

```python
# In router.broadcast():
if flow_aware:
    suppress_check = should_suppress(user_id, priority)
    if suppress_check["should_suppress"]:
        return queue_for_later(user_id, content, priority, channel)
```

### With Scheduler (`tools/automation/scheduler.py`)

Scheduled notifications use transition calculator:

```python
# When scheduling a reminder for an event:
reminder_time = calculate_reminder_time(user_id, event_time, event_type)
schedule_notification(user_id, content, reminder_time)
```

### With ADHD Response Formatter (`tools/adhd/response_formatter.py`)

Batched notifications use ADHD-friendly formatting:

```python
# When releasing suppressed notifications:
if batch_count > 1:
    summary = format_notification_batch(notifications)
    # "3 things came in while you were focused..."
```

---

## Verification Checklist

### Flow Detector
- [ ] `flow_detector.py` passes `python -m py_compile`
- [ ] `--action detect` correctly identifies flow from activity patterns
- [ ] `--action set-override` creates focus mode with duration
- [ ] `--action clear-override` removes focus mode
- [ ] `--action record` updates activity_patterns table
- [ ] Flow score calculation uses configurable thresholds
- [ ] Manual override takes precedence over detected flow

### Transition Calculator
- [ ] `transition_calculator.py` passes `python -m py_compile`
- [ ] `--action calculate` returns correct reminder time
- [ ] Default buffers are ADHD-appropriate (25+ minutes)
- [ ] `--action record` stores actual transition times
- [ ] Learning adjusts buffers based on history (with min samples)
- [ ] Different event types use different default buffers

### Notify Extensions
- [ ] `notify.py` maintains backward compatibility
- [ ] `--flow-aware` flag suppresses during flow
- [ ] `--action check-flow` returns correct suppression status
- [ ] `--action suppressed-count` shows queued notifications
- [ ] `--action release-suppressed` delivers queued items
- [ ] Suppression respects priority tiers from config

### Configuration
- [ ] `smart_notifications.yaml` has all required sections
- [ ] Config loads with sensible defaults if file missing
- [ ] All threshold values are documented

### Integration
- [ ] Flow detector integrates with notify.py
- [ ] Transition calculator can be called from scheduler
- [ ] Database migrations create all required tables
- [ ] Indexes exist for common query patterns

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Flow detector unavailable | Fall back to allowing notifications |
| Config file missing | Use hardcoded ADHD-friendly defaults |
| Database connection fails | Log error, allow notification through |
| Invalid priority | Reject with clear error message |
| Transition calculation fails | Use default buffer for event type |

---

## Testing Scenarios

1. **Flow Interruption Protection**
   - User sends 5 messages in 10 minutes (high activity)
   - Low-priority notification arrives
   - Expected: Notification suppressed, queued

2. **Urgent Override**
   - User in manual focus mode
   - Urgent notification arrives
   - Expected: Notification delivered immediately

3. **Transition Time Learning**
   - User consistently takes 28 minutes for meetings
   - After 5+ samples, system should adjust default
   - Expected: Buffer increases to ~28 minutes

4. **Batch Release**
   - User exits flow state (activity drops)
   - 4 suppressed notifications in queue
   - Expected: Digest notification sent, not 4 separate pings

---

## Anti-Patterns to Avoid

| Don't Do This | Why It Fails |
|---------------|--------------|
| Stack notifications during flow | Creates "notification debt" anxiety |
| Release queue immediately on flow end | Interrupts the natural break |
| Use same buffer for all event types | Deep work needs more transition time |
| Ignore manual focus mode for "important" items | User said they're focusing |
| Show count of missed notifications | Number creates guilt |

---

*Phase 4 protects the ADHD user's most valuable asset: their hyperfocus.*
