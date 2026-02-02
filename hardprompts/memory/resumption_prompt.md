# Hardprompt: Generate ADHD-Friendly Resumption Prompt

## Purpose
Generate a friendly, forward-facing "you were here..." prompt to help ADHD users recover context after interruptions.

## Input Variables
- `{{active_file}}` — File the user was working on (may be "Not specified")
- `{{last_action}}` — What the user just completed
- `{{next_step}}` — What the user was about to do
- `{{age_description}}` — How long ago (e.g., "45 minutes ago", "yesterday")
- `{{channel}}` — Where the activity occurred (optional)

## Instructions

Generate a brief, warm resumption prompt that helps the user pick up where they left off.

**CRITICAL TONE RULES:**

1. **Never use guilt language:**
   - FORBIDDEN: "you still haven't", "you left", "you abandoned", "you forgot"
   - FORBIDDEN: "overdue", "behind", "delayed", "waiting"
   - FORBIDDEN: Any phrasing that implies failure or missed expectations

2. **Always be forward-facing:**
   - GOOD: "Ready to pick up..." / "Want to continue with..."
   - BAD: "You stopped in the middle of..." / "You left off at..."

3. **Frame as opportunity, not obligation:**
   - GOOD: "You were making good progress on X"
   - BAD: "You need to finish X"

4. **Keep it brief:**
   - 1-2 sentences maximum
   - One concrete suggestion, not a list
   - Let the user ask for more if they want

5. **Handle stale contexts gracefully:**
   - If it's been days: "This is from a while back - still relevant?"
   - Don't make them feel bad for taking a break

**Output Format:**

Return a JSON object:
```json
{
  "resumption_prompt": "The friendly prompt (1-2 sentences)",
  "suggested_action": "One concrete next step"
}
```

**Examples:**

Input:
- active_file: "/home/user/project/api/auth.py"
- last_action: "Finished writing the JWT validation middleware"
- next_step: "Wire up the endpoints to use the new middleware"
- age_description: "45 minutes ago"

Output:
```json
{
  "resumption_prompt": "You were working on auth.py - just finished the JWT middleware. Ready to wire up the endpoints?",
  "suggested_action": "Open auth.py and add the middleware to the endpoint routes"
}
```

Input:
- active_file: "Not specified"
- last_action: "Researching deployment options"
- next_step: "Not specified"
- age_description: "3 days ago"

Output:
```json
{
  "resumption_prompt": "A few days ago you were looking into deployment options. Want to pick that back up, or move on to something else?",
  "suggested_action": "Review deployment notes and decide on approach"
}
```

---

## Context to Process

Active file: {{active_file}}
Last action: {{last_action}}
Next step: {{next_step}}
Time since: {{age_description}}
Channel: {{channel}}
