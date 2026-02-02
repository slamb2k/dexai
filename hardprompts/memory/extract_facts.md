# Hardprompt: Extract Facts from Text

## Purpose
Parse unstructured text and extract discrete, storable facts for the memory system.

## Input
- `{{text}}` — Raw text to extract facts from (conversation, document, etc.)

## Instructions

Analyze the following text and extract all distinct facts, preferences, and relationships.

**Requirements:**
1. Each fact should be atomic — one piece of information per entry
2. Preserve specificity — include names, numbers, dates when present
3. Distinguish between:
   - **fact** — Objective information ("Project uses PostgreSQL")
   - **preference** — User preferences ("User prefers TypeScript over JavaScript")
   - **relationship** — Connections between entities ("Alice manages the API team")
   - **insight** — Learned patterns ("Rate limits appear after 100 requests/min")
4. Skip opinions, speculation, and uncertain statements
5. Skip information that is too generic to be useful

**Output Format:**
Return a JSON array of objects:
```json
[
  {
    "type": "fact|preference|relationship|insight",
    "content": "The extracted fact",
    "importance": 1-10,
    "tags": ["optional", "tags"]
  }
]
```

**Importance Guidelines:**
- 9-10: Critical project info, user safety preferences
- 7-8: Important technical decisions, strong preferences
- 5-6: Useful context, moderate preferences
- 3-4: Minor details, weak preferences
- 1-2: Trivial or likely temporary information

**Examples:**

Input: "I'm working on the DexAI project. We use Python with FastAPI. I really hate dealing with YAML configs — always prefer JSON."

Output:
```json
[
  {"type": "fact", "content": "Working on DexAI project", "importance": 7, "tags": ["project"]},
  {"type": "fact", "content": "Project uses Python with FastAPI", "importance": 8, "tags": ["tech-stack", "python"]},
  {"type": "preference", "content": "Prefers JSON over YAML for configs", "importance": 6, "tags": ["preference", "config"]}
]
```

---

## Text to Extract From

{{text}}
