# Phase 3: ADHD Communication Mode

> **Objective**: Transform all DexAI responses into ADHD-friendly communication that is brief by default, RSD-safe, and provides single actionable items when asked "what should I do?"

---

## Rationale

ADHD users face specific communication challenges that standard AI assistants ignore:

1. **Decision Fatigue**: Lists of options paralyze rather than help. Five choices = zero choices.
2. **RSD (Rejection Sensitive Dysphoria)**: Guilt-inducing language ("overdue", "you haven't") triggers shame spirals and system avoidance.
3. **Brevity Needs**: Long responses lose attention. The first sentence is often all that gets read.
4. **Recoverable Depth**: When hyperfocused or curious, users want MORE detail — but only on demand.

This phase ensures every DexAI response respects these constraints by default.

---

## Dependencies

- **Phase 0 (Security)**: Rate limiting, audit logging for tracking communication patterns
- **Phase 1 (Channels)**: Message routing infrastructure to apply formatting consistently

---

## Components to Build

### 1. Package Init (`tools/adhd/__init__.py`)
- Package constants (PROJECT_ROOT, CONFIG_PATH)
- Docstring explaining ADHD communication philosophy

### 2. Response Formatter (`tools/adhd/response_formatter.py`)
Core formatting engine that enforces ADHD-friendly output:
- **Default brevity**: Cap responses at 1-2 sentences
- **Expand on demand**: Track "more" keyword to unlock detail
- **One-thing mode**: Extract THE single actionable item from any task list
- **No preamble**: Strip filler like "Sure!", "Of course!", "Great question!"

CLI interface:
```bash
python tools/adhd/response_formatter.py --action format --content TEXT
python tools/adhd/response_formatter.py --action expand --content TEXT --user USER
python tools/adhd/response_formatter.py --action one-thing --content TEXT
```

### 3. Language Filter (`tools/adhd/language_filter.py`)
RSD protection layer that detects and reframes harmful language:
- **Blocked phrases**: Detect guilt-inducing patterns
- **Reframe mappings**: Convert to forward-facing alternatives
- **Tone check**: Flag responses that would trigger shame

CLI interface:
```bash
python tools/adhd/language_filter.py --action filter --content TEXT
python tools/adhd/language_filter.py --action check --content TEXT
```

### 4. Configuration (`args/adhd_mode.yaml`)
User-adjustable settings for ADHD mode:
- Brevity rules (max sentences, expand keywords)
- One-thing mode toggle
- RSD protection settings (blocked phrases, reframe patterns)
- Tone preferences

### 5. Hardprompts (`hardprompts/adhd/`)
LLM instruction templates:
- `brevity_instructions.md`: Keep responses short
- `rsd_reframe.md`: Transform guilt language
- `one_thing_selection.md`: Select the single best action

---

## Implementation Order

1. Create `tools/adhd/__init__.py` with path constants
2. Create `args/adhd_mode.yaml` with default configuration
3. Build `tools/adhd/language_filter.py` (RSD protection first)
4. Build `tools/adhd/response_formatter.py` (depends on language filter)
5. Create hardprompts for LLM guidance
6. Update `tools/manifest.md` with new tools
7. Update `goals/manifest.md` with Phase 3 status

---

## Database Schema

No new database tables. ADHD mode uses configuration files and stateless transformations.

User preferences (which user requested "more" recently) are tracked in the existing `data/preferences.db` via the inbox tool.

---

## Verification Checklist

### Brevity Tests
- [ ] Default response to any question is 1-2 sentences max
- [ ] Response contains no preamble ("Sure!", "Of course!")
- [ ] "more" keyword triggers expanded response (tracked per-user)
- [ ] "explain" keyword also triggers expansion
- [ ] Expanded response still omits guilt language

### RSD-Safety Tests
- [ ] "overdue" is NEVER present in any output
- [ ] "you haven't" is NEVER present in any output
- [ ] "you still haven't" is NEVER present in any output
- [ ] "failed to" is NEVER present in any output
- [ ] "you forgot" is NEVER present in any output
- [ ] "missed deadline" is NEVER present in any output
- [ ] "behind schedule" is NEVER present in any output
- [ ] All reframes are forward-facing ("ready when you are", "want to tackle")

### One-Thing Tests
- [ ] "What should I do?" returns EXACTLY ONE action
- [ ] The action is specific and concrete (not "work on the project")
- [ ] The action has friction pre-removed where possible
- [ ] User can say "something else" to get alternative
- [ ] No lists are ever shown by default

### Integration Tests
- [ ] Formatter integrates with router.py message pipeline
- [ ] Language filter runs before final response
- [ ] Configuration loads from args/adhd_mode.yaml
- [ ] CLI tools return proper JSON output
- [ ] All tools have --help documentation

---

## Example Transformations

### Brevity

**Before (typical AI):**
> "That's a great question! So, there are actually several ways you could approach this problem. First, you might want to consider..."

**After (ADHD mode):**
> "Check the API docs first. Say 'more' for details."

### RSD-Safe Reframing

**Before (guilt-inducing):**
> "You still haven't sent the invoice that was due 3 days ago. The deadline has passed and the client is waiting."

**After (forward-facing):**
> "Ready to send that invoice when you are. Want me to draft it now?"

### One-Thing Selection

**User asks:** "What should I do?"

**Before (overwhelming list):**
> "Here are your priorities:
> 1. Send invoice to client
> 2. Review pull request
> 3. Schedule meeting with team
> 4. Update project documentation
> 5. Respond to Sarah's email"

**After (one thing):**
> "Send the invoice to Marcus. Here's a draft ready to go."

---

## Configuration Reference

See `args/adhd_mode.yaml` for full configuration options:
- `brevity.default_max_sentences`: Number of sentences in default response
- `brevity.expand_on_keywords`: Words that trigger expanded response
- `one_thing.enabled`: Whether to enforce single-action responses
- `rsd_protection.blocked_phrases`: Phrases that must never appear
- `rsd_protection.reframe_patterns`: Before/after mappings

---

## Notes

- This phase is foundational — every subsequent phase depends on ADHD-safe communication
- The language filter should be applied at the VERY END of the response pipeline
- Never rely on users to configure this — it must work perfectly out of the box
- Monitor for phrases that slip through and add to blocked list

---

*Phase 3 of 8 in DexAI implementation roadmap*
