# Hardprompt: RSD-Safe Language Reframing

## Purpose
Transform guilt-inducing language into forward-facing alternatives that won't trigger Rejection Sensitive Dysphoria (RSD) in ADHD users.

## Input
- `{{content}}` - Text that may contain guilt/shame language

## Background

RSD (Rejection Sensitive Dysphoria) is an extreme emotional sensitivity common in ADHD. Standard productivity language like "overdue" or "you haven't" can trigger:
- Shame spirals
- Task avoidance
- System abandonment

The goal is to convey the SAME INFORMATION with forward-facing tone.

## Instructions

Rewrite the following text to be RSD-safe:

1. **Never use backward-looking blame:**
   - ❌ "overdue", "past due", "late"
   - ❌ "you haven't", "you still haven't"
   - ❌ "you forgot", "you missed"
   - ❌ "failed to", "neglected"
   - ❌ "behind schedule", "missed deadline"

2. **Always use forward-facing alternatives:**
   - ✅ "ready when you are"
   - ✅ "want to tackle this?"
   - ✅ "let's pick this up"
   - ✅ "ready to send"
   - ✅ "let's reschedule"

3. **Preserve the information** - the user still needs to know about pending items
4. **Offer help** - "want me to draft it?" reduces friction
5. **Keep it casual** - friendly tone, not formal/stern

**Format:** Return ONLY the reframed text, no explanation.

---

## Reframe Patterns

| ❌ Guilt-Inducing | ✅ Forward-Facing |
|-------------------|-------------------|
| "The invoice is overdue" | "The invoice is ready to send" |
| "You still haven't replied to Sarah" | "Ready to reply to Sarah when you are" |
| "You forgot to call the client" | "Want to call the client now?" |
| "The deadline was missed" | "Let's get this moving" |
| "You're behind schedule" | "Let's catch up on this" |
| "You failed to submit the report" | "The report is ready to submit" |
| "Why haven't you finished this?" | "Want to wrap this up?" |
| "This was due yesterday" | "This is ready to go" |
| "You neglected to update the docs" | "Let's update the docs" |
| "You should have done this earlier" | "Let's do this now" |

---

## Examples

### Example 1: Task Reminder

**Input:**
```
You still haven't sent the invoice that was due 3 days ago. The deadline has passed and the client is waiting.
```

**Output:**
```
Ready to send that invoice when you are. Want me to draft it now?
```

### Example 2: Multiple Items

**Input:**
```
You have 5 overdue tasks. You forgot to reply to Sarah, missed the deadline for the report, haven't updated your timesheet in a week, failed to schedule the team meeting, and still need to review the PR from Monday.
```

**Output:**
```
You've got a few things ready to tackle. Want to start with replying to Sarah? I can help draft it.
```

### Example 3: Gentle Reminder

**Input:**
```
Just a reminder that you were supposed to call Marcus yesterday but you didn't. He's probably wondering why you haven't reached out.
```

**Output:**
```
Marcus is ready for that call when you are. Want me to send him a quick message first?
```

### Example 4: Project Status

**Input:**
```
The project is behind schedule. You missed the last two milestones and haven't made progress on the API integration that was due last week. The team is waiting on you.
```

**Output:**
```
Let's catch up on the project. The API integration is ready to pick up - want to start there?
```

### Example 5: Returning User

**Input:**
```
You haven't logged in for 5 days. Your task list has been piling up and several deadlines have passed while you were away.
```

**Output:**
```
Good to see you! Ready to pick up where you left off. Want me to surface the most important thing?
```

---

## Content to Reframe

{{content}}
