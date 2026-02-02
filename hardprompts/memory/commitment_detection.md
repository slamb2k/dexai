# Hardprompt: Extract Commitments from Conversation

## Purpose
Parse conversation text and extract commitments (promises, obligations) that should be tracked to prevent them from falling through the cracks.

## Input Variables
- `{{text}}` — The conversation text to analyze
- `{{user_name}}` — The user's name (to identify their commitments vs others')

## Instructions

Analyze the text and extract all commitments made BY the user. A commitment is a promise to do something for someone else or themselves.

**What counts as a commitment:**

1. **Explicit promises:**
   - "I'll send you the docs"
   - "I will review that PR"
   - "I promise to call you back"

2. **Implicit commitments:**
   - "Let me check on that" (implies follow-up)
   - "I'll get back to you" (promise to respond)
   - "I can do that" (agreement to task)

3. **Time-bound commitments:**
   - "I'll do it tomorrow"
   - "By end of week"
   - "After the meeting"

**What does NOT count:**

1. Questions: "Should I send you the docs?"
2. Hypotheticals: "I could send you the docs if needed"
3. Past actions: "I sent you the docs yesterday"
4. Other people's commitments: "She said she'd review it"

**Extraction Rules:**

1. Each commitment should be self-contained (understandable without context)
2. Include the target person if mentioned
3. Extract due dates/timeframes if present
4. Assign confidence: high (explicit promise), medium (implied), low (uncertain)
5. Skip commitments that are too vague to be actionable

**Output Format:**

Return a JSON array of commitment objects:
```json
[
  {
    "content": "Send Sarah the API documentation",
    "target_person": "Sarah",
    "due_date": "tomorrow",
    "confidence": "high",
    "original_text": "I'll send you the API docs tomorrow, Sarah"
  }
]
```

**Examples:**

Input text:
"Hey Sarah, I'll send you the API docs tomorrow. Also, let me check if the tests are passing and get back to you. Bob said he'd handle the deployment."

Output:
```json
[
  {
    "content": "Send the API documentation",
    "target_person": "Sarah",
    "due_date": "tomorrow",
    "confidence": "high",
    "original_text": "I'll send you the API docs tomorrow"
  },
  {
    "content": "Check if tests are passing and follow up",
    "target_person": "Sarah",
    "due_date": null,
    "confidence": "medium",
    "original_text": "let me check if the tests are passing and get back to you"
  }
]
```

Note: "Bob said he'd handle the deployment" is NOT extracted because it's someone else's commitment.

---

## Text to Analyze

User: {{user_name}}

Text:
{{text}}
