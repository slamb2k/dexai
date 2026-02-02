# Hardprompt: Summarize Memory Entry

## Purpose
Compress verbose memory entries into concise, searchable summaries while preserving key information.

## Input
- `{{content}}` — The full memory entry content to summarize

## Instructions

Summarize the following memory entry into 1-2 sentences (max 200 characters).

**Requirements:**
1. Preserve the core fact, preference, or insight
2. Remove filler words, redundancy, and unnecessary context
3. Use active voice and present tense where possible
4. Keep proper nouns and specific values intact
5. Make it scannable — front-load the key information

**Format:** Return ONLY the summary, no preamble or explanation.

**Examples:**

Input: "The user mentioned during our conversation yesterday that they really prefer to have dark mode enabled on all their applications because it's easier on their eyes, especially when working late at night."
Output: "User prefers dark mode for reduced eye strain during night work."

Input: "I learned that the project is using Python 3.11 with FastAPI for the backend API development, and they're planning to eventually migrate to Python 3.12 when it becomes more stable."
Output: "Project uses Python 3.11 + FastAPI backend; planning Python 3.12 migration."

---

## Memory Entry to Summarize

{{content}}
