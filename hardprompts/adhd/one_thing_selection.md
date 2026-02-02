# Hardprompt: One-Thing Selection for ADHD Users

## Purpose
When user asks "what should I do?", select THE SINGLE most important action from available options. ADHD decision fatigue means a list of five things is actually zero things.

## Input
- `{{tasks}}` - List of possible tasks or options
- `{{user_energy}}` - Optional: current energy level (high/medium/low)
- `{{time_available}}` - Optional: time available (e.g., "15 minutes", "2 hours")
- `{{context}}` - Optional: any relevant context about user's state

## Instructions

Your job is to select **exactly ONE action** for the user.

**Selection Criteria (in order of priority):**

1. **Urgency** - Is something time-sensitive right now?
2. **Friction** - What has the lowest barrier to start?
3. **Energy match** - Does it fit the user's current capacity?
4. **Momentum potential** - Will completing it unlock other things?
5. **Emotional weight** - Avoid the thing causing the most anxiety (that often needs a different approach)

**Response Requirements:**

1. Return **exactly ONE action** - never a list
2. Make it **specific and concrete** - not "work on the project"
3. **Remove friction** - include any setup info they need
4. Offer **escape hatch** - "Say 'something else' for an alternative"
5. **No justification by default** - just the action (unless they ask why)

**Format:** Return the single action in 1-2 sentences, plus the escape hatch.

---

## Examples

### Example 1: Standard Task List

**Input:**
```
Tasks:
- Send invoice to Marcus ($450, consulting)
- Review pull request from Alex (bug fix)
- Schedule team meeting for next week
- Update project documentation
- Reply to Sarah's email about the workshop

User energy: medium
Time available: 30 minutes
```

**Output:**
```
Send the invoice to Marcus - here's a draft ready to go. Say 'something else' for an alternative.
```

### Example 2: Low Energy State

**Input:**
```
Tasks:
- Write quarterly report (needs research)
- Refactor authentication module
- Reply to 3 emails
- Update LinkedIn profile
- Review expense receipts

User energy: low
Time available: 1 hour
```

**Output:**
```
Reply to one email - the shortest one. Say 'something else' for an alternative.
```

### Example 3: Time Pressure

**Input:**
```
Tasks:
- Prepare slides for 2pm meeting (it's 1:30pm now)
- Review contract before signing
- Schedule dentist appointment
- Fix bug in production
- Update weekly status report

User energy: high
Time available: 25 minutes
Context: Meeting in 30 minutes
```

**Output:**
```
Open your slides and review the 3 key points you want to make. Say 'something else' for an alternative.
```

### Example 4: Overwhelming List

**Input:**
```
Tasks:
- Clean apartment
- Do laundry
- Pay bills
- Call mom
- Exercise
- Meal prep
- Organize desk
- Update resume
- Learn new skill
- Read book

User energy: medium
Time available: unknown
Context: User said "I'm overwhelmed"
```

**Output:**
```
Do one load of laundry - just put clothes in the machine, nothing else. Say 'something else' for an alternative.
```

### Example 5: User Rejected First Suggestion

**Input:**
```
Tasks: [same as above]
Context: User said "something else" to the laundry suggestion
```

**Output:**
```
Pay one bill - the smallest one. 5 minutes. Say 'something else' if that doesn't feel right either.
```

### Example 6: High Stakes Items

**Input:**
```
Tasks:
- Submit tax return (deadline tomorrow)
- Prepare for job interview (tomorrow 10am)
- Reply to urgent client email
- Book flight for next week
- Finish presentation draft

User energy: medium
Time available: 3 hours
```

**Output:**
```
Open TurboTax and review your return - submit it tonight. Say 'something else' for an alternative.
```

---

## Selection Process (Internal)

When multiple items seem equally important:

1. **If one is time-sensitive today** → pick that
2. **If all are time-sensitive** → pick the shortest one
3. **If none are time-sensitive** → pick the lowest-friction one
4. **If user is low energy** → pick something that takes <10 minutes
5. **If user is overwhelmed** → pick something physical/simple
6. **If user rejects suggestion** → pick something in a different category

Never explain this process unless asked.

---

## Tasks to Evaluate

**User energy:** {{user_energy}}
**Time available:** {{time_available}}
**Context:** {{context}}

**Tasks:**
{{tasks}}
