# Memory, Context & Compaction System Design

**Status:** Design
**Depends on:** Phase 0 (Security), Phase 2 (Working Memory), Memory Providers Architecture
**Last Updated:** 2026-02-10

---

## Problem Statement

DexAI's current memory system stores and retrieves memories effectively within a session, but lacks a cohesive strategy for:

1. **Short-term memory beyond the conversation** — Messages in the current context window are lost after compaction or session end. No mechanism captures important information as it flows through the conversation.
2. **Compaction survival** — When Claude's context window fills and auto-compaction fires, nuanced facts, instructions, and decisions are paraphrased into lossy summaries. There is no PostCompact hook to re-inject critical context.
3. **Memory lifecycle management** — No system for detecting when new facts supersede old ones, archiving stale memories, or consolidating redundant entries over time.
4. **Provider-agnostic operations** — External providers (Mem0, Zep) have built-in deduplication and supersession, but the native provider lacks these capabilities. The common interface needs to support all lifecycle operations regardless of backend.
5. **User experience impact** — Memory operations (extraction, embedding, consolidation) cannot add perceptible latency to the conversation.

This document designs a unified system that addresses all five concerns while aligning with Claude Agent SDK capabilities and ADHD-first design principles.

---

## Architecture Overview

### The Three-Tier Memory Model (L1 / L2 / L3)

Inspired by MemGPT's OS metaphor and the emerging consensus in agent memory research (SimpleMem, H-MEM, Letta), DexAI adopts a three-tier memory hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          L1: HOT MEMORY (In-Context)                       │
│                                                                             │
│  Always visible to the LLM. No retrieval needed.                           │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐  │
│  │ System Prompt │  │ User Profile │  │ Active Context Block             │  │
│  │ (CLAUDE.md,  │  │ (name, prefs,│  │ (current task, recent decisions, │  │
│  │  ADHD rules) │  │  energy, key │  │  active commitments, session     │  │
│  │              │  │  facts)      │  │  notes from memory search)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ Conversation Buffer (last N messages — managed by SDK compaction)    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  Budget: ~4K tokens for memory blocks + conversation buffer                │
│  Latency: 0ms (already in context)                                         │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                     page in (search) │ page out (extract + persist)
                                     │
┌────────────────────────────────────▼────────────────────────────────────────┐
│                        L2: WARM MEMORY (Fast Retrieval)                    │
│                                                                             │
│  Indexed for fast keyword + semantic search. Cross-session.                │
│                                                                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ Session Notes    │  │ Extracted Facts   │  │ Commitments & Promises  │  │
│  │ (per-turn LLM   │  │ (preferences,     │  │ (tracked with due dates,│  │
│  │  distillation)   │  │  relationships,   │  │  target people, status) │  │
│  │                  │  │  events, insights) │  │                         │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Context Snapshots (working state captured on task switch / idle)    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Storage: SQLite (native) / Mem0 / Zep (provider-dependent)                │
│  Search: Hybrid BM25 + semantic (native) / provider-native search          │
│  Latency: <200ms retrieval                                                  │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                  consolidate (async) │ archive (background)
                                     │
┌────────────────────────────────────▼────────────────────────────────────────┐
│                        L3: COLD MEMORY (Archival)                          │
│                                                                             │
│  Long-term storage. Semantic search only. Background consolidation.        │
│                                                                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ Consolidated     │  │ Superseded Facts  │  │ Full Conversation Logs  │  │
│  │ Memories         │  │ (invalid_at set,  │  │ (raw transcripts,       │  │
│  │ (clusters merged │  │  preserved for    │  │  compaction summaries)  │  │
│  │  into abstracts) │  │  temporal queries) │  │                         │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│                                                                             │
│  Storage: Vector DB (native embeddings) / Mem0 archival / Zep graph        │
│  Search: Semantic only, slower                                              │
│  Latency: <1s retrieval                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

```
User Message
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    HOT PATH (synchronous)                            │
│                                                                      │
│  1. Auto-recall: inject relevant L2 memories into L1 context        │
│  2. LLM generates response using L1 context                        │
│  3. Response delivered to user                                       │
│                                                                      │
│  Latency budget: <200ms for memory injection                        │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   WARM PATH (async, per-turn)                        │
│                                                                      │
│  4. Heuristic gate: does this turn contain memorable content?       │
│  5. If yes: extract session notes (cheap LLM or heuristic)         │
│  6. Persist to L2 store via memory provider                         │
│  7. Update L1 user profile block if significant preference change   │
│                                                                      │
│  Runs after response is delivered. User never waits.                │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   COLD PATH (background daemon)                      │
│                                                                      │
│  8. Periodic consolidation: cluster related L2 memories             │
│  9. Supersession check: invalidate stale facts                      │
│  10. Archive expired memories to L3                                 │
│  11. Rebuild user profile summary for L1 injection                  │
│                                                                      │
│  Runs on schedule (hourly/daily). Zero user impact.                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. Memory Extraction Pipeline

#### 1.1 The Heuristic Gate (Pre-Filter)

Not every message deserves memory extraction. A lightweight heuristic gate runs on every turn to decide whether to trigger extraction, avoiding unnecessary LLM calls.

**Signals that trigger extraction:**

| Signal | Detection Method | Cost |
|--------|-----------------|------|
| Named entities | Regex + spaCy NER (if available) | ~1ms |
| Temporal references | Regex: "tomorrow", "next week", "at 3pm" | <1ms |
| Possessive pronouns without antecedent | "my doctor", "our project" | <1ms |
| Commitment language | "I'll", "I promise", "remind me to", "don't forget" | <1ms |
| Preference statements | "I prefer", "I like", "I always", "I never" | <1ms |
| Emotional significance | "I'm worried", "I'm excited", "this is important" | <1ms |
| Factual assertions | "I am", "I work at", "I live in", "I have" | <1ms |
| Semantic divergence from recent context | Embedding distance > threshold | ~50ms |
| Entity novelty | New entities not seen in last N messages | ~5ms |

**Gate decision logic:**

```python
def should_extract(message: str, recent_context: list[str]) -> tuple[bool, float]:
    """
    Decide whether this message warrants memory extraction.

    Returns:
        (should_extract, confidence_score)
    """
    score = 0.0

    # Fast regex signals (< 1ms total)
    if has_commitment_language(message):
        score += 0.4
    if has_preference_statement(message):
        score += 0.3
    if has_temporal_reference(message):
        score += 0.2
    if has_named_entities(message):
        score += 0.2
    if has_factual_assertion(message):
        score += 0.2
    if has_emotional_significance(message):
        score += 0.1

    # Slightly more expensive signals (< 50ms)
    if score >= 0.2:  # Only check if fast signals fired
        novelty = calculate_entity_novelty(message, recent_context)
        score += novelty * 0.3

    # Threshold: 0.3 = at least one strong signal or two weak ones
    return score >= 0.3, score
```

**Why a heuristic gate instead of always extracting:**
- Saves ~$0.001-0.01 per skipped LLM extraction call
- At 100+ messages/day, this adds up
- Most conversational filler ("ok", "thanks", "got it") has zero memory value
- SimpleMem research shows 56.7% of conversation windows are below their information threshold

#### 1.2 Session Note Extraction

When the gate fires, a lightweight LLM call extracts structured session notes from the turn.

**Extraction approach — two options by provider:**

| Provider | Extraction Method | Cost |
|----------|------------------|------|
| **Native** | Local LLM call (Haiku) with extraction prompt | ~$0.0005/call |
| **Mem0** | `memory.add(messages, user_id, infer=True)` — built-in extraction pipeline | Included |
| **Zep** | `thread.add_messages()` — automatic graph ingestion | Included |

**For the native provider, the extraction prompt:**

```
Given this conversation turn, extract any facts worth remembering long-term.
For each fact, classify it and rate its importance (1-10).

Categories: FACT, PREFERENCE, EVENT, INSIGHT, RELATIONSHIP, COMMITMENT

Rules:
- Only extract genuinely new or updated information
- Skip greetings, acknowledgments, and filler
- Commitments must include: what, who (if mentioned), when (if mentioned)
- Rate importance: 1-3 mundane, 4-6 useful, 7-9 significant, 10 critical

User message: {user_message}
Assistant response: {assistant_response}
```

**When extraction runs:**
- After the response is delivered to the user (async, never blocking)
- Triggered by the heuristic gate scoring above threshold
- Uses the cheapest available model (Haiku for native, built-in for Mem0/Zep)

#### 1.3 Commitment Extraction

Commitments (promises, reminders, follow-ups) are a special case requiring dedicated handling because they have deadlines and target people.

The existing `commitments.py` module handles this well. The integration point is:
- The heuristic gate detects commitment language
- If detected, route to `extract_commitments()` in addition to general extraction
- Commitments are stored in L2 with their own table/schema
- The commitment surfacing system (Phase 4) handles reminders

### 2. Compaction Integration

#### 2.1 Current SDK Hook Landscape

| Hook | Available | Our Use |
|------|-----------|---------|
| `PreCompact` | Yes (Python + TS SDK) | Back up conversation, extract remaining memories |
| PostCompact | **No** (heavily requested, not implemented) | N/A — must work around |
| `PreToolUse` | Yes | Existing security hooks |
| `PostToolUse` | Yes | Memory extraction trigger |
| `UserPromptSubmit` | Yes | Post-compaction context re-injection workaround |
| `Stop` | Yes | Session-end memory consolidation |

#### 2.2 PreCompact Hook — Memory Checkpoint

When compaction is about to fire, we save everything important before the conversation gets summarized.

```python
async def pre_compact_handler(input_data):
    """
    Fires before context compaction. Saves conversation state to L2 memory.

    Receives:
        trigger: "manual" | "auto"
        custom_instructions: str | None (for manual /compact)
        transcript_path: str (path to full transcript JSONL)
    """
    trigger = input_data.get("trigger", "auto")
    transcript_path = input_data.get("transcript_path", "")

    # 1. Back up raw transcript to L3 (archival)
    if transcript_path:
        await archive_transcript(transcript_path, trigger)

    # 2. Extract any remaining un-extracted memories from recent turns
    await flush_extraction_queue()

    # 3. Capture a context snapshot (current task state)
    await capture_pre_compaction_snapshot(trigger)

    # 4. Write a marker file for UserPromptSubmit to detect
    write_compaction_marker()

    return {}  # Allow compaction to proceed
```

#### 2.3 Post-Compaction Context Re-Injection (Workaround)

Since PostCompact doesn't exist, we use the `UserPromptSubmit` hook to detect when compaction just happened and re-inject critical context.

```python
async def user_prompt_submit_handler(input_data):
    """
    Fires on every user message. Checks if compaction just occurred
    and injects memory context if so.
    """
    if not compaction_marker_exists():
        return {}  # No compaction happened, pass through

    # Compaction just happened — re-inject critical context
    clear_compaction_marker()

    # Build a condensed memory block for the system prompt
    user_id = get_current_user_id()
    memory_block = await build_l1_memory_block(user_id)

    # Inject as a system message that Claude will see
    return {
        "systemMessage": memory_block
    }
```

**What the re-injected memory block contains:**
- User profile summary (name, key preferences, energy level)
- Active task state (from pre-compaction snapshot)
- Top 3-5 most relevant memories for the current conversation topic
- Active commitments due soon
- Any custom instructions from the compaction trigger

**Important limitation:** The `systemMessage` from `UserPromptSubmit` becomes part of the conversation context. It will itself be subject to future compaction. This is acceptable because:
- The underlying L2 memories persist regardless
- The block is rebuilt fresh after each compaction
- It's kept concise (~500-1000 tokens) to minimize context waste

#### 2.4 Server-Side Compaction Configuration

When DexAI controls the API call loop (via `SessionManager` / `DexAIClient`), use the server-side `context_management` parameter for better control:

```python
response = client.beta.messages.create(
    betas=["compact-2026-01-12"],
    model=model_id,
    max_tokens=max_tokens,
    messages=messages,
    context_management={
        "edits": [{
            "type": "compact_20260112",
            "trigger": {"type": "input_tokens", "value": 80000},
            "instructions": (
                "Preserve: current task state, user preferences, "
                "active commitments, key technical decisions. "
                "Discard: routine greetings, tool output details, "
                "intermediate reasoning steps."
            ),
            "pause_after_compaction": True
        }]
    }
)

# Handle compaction pause
if response.stop_reason == "compaction":
    # Inject post-compaction context
    memory_block = await build_l1_memory_block(user_id)
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": f"[Memory context restored]\n{memory_block}"})
    # Continue with next request
```

**Why trigger at 80K tokens instead of 150K default:**
- JetBrains research shows earlier compaction preserves more working memory
- 80K leaves headroom for the model to work without pressure
- More frequent, smaller compactions are less lossy than one large compaction

#### 2.5 Proactive Compaction Strategy

Rather than waiting for auto-compaction, DexAI should compact proactively at strategic moments:

| Trigger | When | Why |
|---------|------|-----|
| Task completion | After marking a task done | Clean context for next task |
| Topic shift | When conversation topic diverges significantly | Old topic context is noise |
| Token threshold | At 60% of context limit | Prevents emergency compaction |
| User idle | After 5+ minutes of inactivity | Good time for background work |
| Manual | User types `/compact` | Explicit user control |

**Detection of topic shift:** Embedding similarity between the last 3 messages and the current message. If similarity drops below 0.4, suggest or auto-trigger compaction.

### 3. Memory Lifecycle Management

#### 3.1 Supersession Strategy

When new information contradicts or updates existing memories, the old memory must be handled carefully. Drawing from Mem0's AUDN pipeline and Zep's temporal invalidation:

```
New fact arrives
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ Retrieve top-S similar existing memories (S=10)         │
│ (via embedding similarity from L2 store)                │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│ LLM Classification (cheap model: Haiku)                 │
│                                                         │
│ For each (new_fact, existing_memory) pair:               │
│                                                         │
│   ADD       — Genuinely new, no overlap                 │
│   UPDATE    — Augments/refines existing (merge)         │
│   SUPERSEDE — Contradicts existing (invalidate old)     │
│   NOOP      — Duplicate or irrelevant (skip)            │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┼────────────┬───────────┐
              ▼            ▼            ▼           ▼
           ADD          UPDATE      SUPERSEDE     NOOP
         (insert)    (merge into    (mark old     (skip)
                      existing)    as invalid,
                                   insert new)
```

**For the native provider:**

```sql
-- Add supersession tracking to memory_entries
ALTER TABLE memory_entries ADD COLUMN superseded_by TEXT;
ALTER TABLE memory_entries ADD COLUMN superseded_at DATETIME;
ALTER TABLE memory_entries ADD COLUMN valid_from DATETIME DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE memory_entries ADD COLUMN valid_until DATETIME;  -- NULL = still valid

-- Query for current (non-superseded) memories
SELECT * FROM memory_entries
WHERE active = 1 AND superseded_by IS NULL
ORDER BY importance DESC, created_at DESC;

-- Query for historical state at a point in time
SELECT * FROM memory_entries
WHERE valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)
ORDER BY importance DESC;
```

**For external providers:**
- **Mem0**: Built-in AUDN pipeline handles this automatically when `infer=True`
- **Zep**: Temporal invalidation is native — facts get `invalid_at` timestamps automatically

#### 3.2 Consolidation (L2 → L3 Promotion)

Periodic background consolidation clusters related L2 memories into denser L3 abstractions. This prevents L2 from growing unboundedly and improves retrieval quality.

**Consolidation algorithm:**

```python
async def consolidate_memories(user_id: str):
    """
    Run periodically (default: every 24 hours).
    Clusters related L2 memories into L3 abstractions.
    """
    # 1. Fetch all valid L2 memories older than 7 days
    memories = await provider.list(
        user_id=user_id,
        min_age_days=7,
        tier="L2",
        valid_only=True
    )

    # 2. Cluster by embedding similarity
    clusters = cluster_by_similarity(memories, threshold=0.85)

    for cluster in clusters:
        if len(cluster) < 3:
            continue  # Don't consolidate small clusters

        # 3. Generate abstract summary
        abstract = await llm.summarize(
            [m.content for m in cluster],
            prompt="Synthesize these related memories into a single, "
                   "concise fact. Preserve key details and dates."
        )

        # 4. Create consolidated L3 memory
        consolidated_id = await provider.add(
            content=abstract,
            entry_type="INSIGHT",
            importance=max(m.importance for m in cluster),
            tier="L3",
            metadata={
                "source_ids": [m.id for m in cluster],
                "consolidated_from_count": len(cluster),
                "consolidated_at": datetime.now().isoformat()
            }
        )

        # 5. Mark originals as superseded (not deleted)
        for memory in cluster:
            await provider.update(
                memory.id,
                superseded_by=consolidated_id,
                superseded_at=datetime.now()
            )
```

**Consolidation schedule (from `args/memory.yaml`):**
- Default: every 24 hours (configurable via `sync.consolidation_interval_hours`)
- Runs during low-activity periods (default: 3 AM via `cleanup.cleanup_hour`)
- Can be triggered manually via CLI: `dexai memory consolidate`

#### 3.3 Archival and Cleanup

Memories that are no longer relevant should be archived, not deleted. This preserves the ability to answer temporal queries ("what did I prefer last year?").

**Retention policy (from existing `args/memory.yaml`):**

| Type | Retention | Archive? |
|------|-----------|----------|
| FACT | Forever | Yes (on supersession) |
| PREFERENCE | Forever | Yes (on supersession) |
| INSIGHT | Forever | Yes (on consolidation) |
| RELATIONSHIP | Forever | Yes (on supersession) |
| EVENT | 90 days | Yes |
| TASK | 30 days | Yes |
| Session notes | 7 days | No (consumed by consolidation) |
| Context snapshots | 7 days | No (expired snapshots deleted) |

**Cleanup process:**

```python
async def cleanup_memories(user_id: str):
    """
    Run daily. Archives expired memories, removes stale snapshots.
    """
    # 1. Archive expired memories based on retention policy
    expired = await provider.list(
        user_id=user_id,
        expired=True,
        valid_only=True
    )
    for memory in expired:
        await provider.update(memory.id, tier="L3", archived=True)

    # 2. Delete old context snapshots (already consumed)
    await provider.cleanup_snapshots(
        max_age_days=7
    )

    # 3. Delete old session notes (already consolidated)
    await provider.cleanup_session_notes(
        max_age_days=7
    )
```

### 4. Memory Provider Interface

#### 4.1 Extended Provider Interface

The existing `MemoryProvider` base class needs these additions to support the full lifecycle:

```python
class MemoryProvider(ABC):
    """Extended interface for memory lifecycle management."""

    # === Existing methods (already in base.py) ===
    async def add(self, content, entry_type, importance, ...) -> str: ...
    async def search(self, query, filters, limit, ...) -> list[MemoryEntry]: ...
    async def get(self, entry_id) -> MemoryEntry | None: ...
    async def update(self, entry_id, **kwargs) -> bool: ...
    async def delete(self, entry_id, hard=False) -> bool: ...
    async def list(self, filters, ...) -> list[MemoryEntry]: ...
    async def health_check(self) -> HealthStatus: ...

    # === New: Supersession ===
    async def supersede(
        self,
        old_id: str,
        new_content: str,
        reason: str = "updated"
    ) -> str:
        """
        Mark old memory as superseded and create replacement.

        Returns: ID of the new memory.
        """
        ...

    async def classify_update(
        self,
        new_fact: str,
        existing_memories: list[MemoryEntry]
    ) -> list[dict]:
        """
        Classify how new_fact relates to existing memories.

        Returns: List of {action: ADD|UPDATE|SUPERSEDE|NOOP, memory_id, reason}
        """
        ...

    # === New: Tiered Storage ===
    async def promote(self, entry_id: str, target_tier: str) -> bool:
        """Move memory from current tier to target (e.g., L2 → L3)."""
        ...

    async def consolidate(
        self,
        memory_ids: list[str],
        summary: str
    ) -> str:
        """
        Merge multiple memories into a consolidated entry.
        Original memories are marked as superseded.

        Returns: ID of the consolidated memory.
        """
        ...

    # === New: Session Notes ===
    async def add_session_note(
        self,
        content: str,
        session_id: str,
        importance: int = 5,
        metadata: dict | None = None
    ) -> str:
        """Store a session-scoped note for later consolidation."""
        ...

    async def get_session_notes(
        self,
        session_id: str
    ) -> list[MemoryEntry]:
        """Retrieve all notes for a session."""
        ...

    # === New: L1 Context Building ===
    async def build_context_block(
        self,
        user_id: str,
        current_query: str | None = None,
        max_tokens: int = 1000
    ) -> str:
        """
        Build a condensed memory block for L1 injection.
        Combines user profile, relevant memories, and active commitments.
        """
        ...
```

#### 4.2 Provider-Specific Implementations

Each provider maps these operations to its native capabilities:

| Operation | Native | Mem0 | Zep |
|-----------|--------|------|-----|
| `supersede()` | SQL UPDATE + INSERT | `memory.add(infer=True)` handles automatically | `graph.add()` with temporal invalidation |
| `classify_update()` | Local Haiku LLM call | Built into `memory.add()` pipeline | Built into graph ingestion |
| `consolidate()` | SQL bulk update + insert | `memory.add()` with cluster content | `graph.add(type="text")` |
| `add_session_note()` | INSERT with session_id filter | `memory.add(run_id=session_id)` | `thread.add_messages()` |
| `build_context_block()` | Hybrid search + format | `memory.search()` + format | `thread.get_user_context()` |
| `search()` | BM25 + cosine similarity | Vector + metadata filters + optional reranker | Full-text + semantic + graph traversal |

### 5. Background Processing Architecture

#### 5.1 The Memory Daemon

A lightweight background process that handles all non-blocking memory operations. Runs as part of the DexAI backend, not as a separate service.

```
┌─────────────────────────────────────────────────────────────────┐
│                      Memory Daemon                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Extraction Queue                                         │   │
│  │                                                          │   │
│  │  PostToolUse/PostTurn events → Queue → Extract → Store   │   │
│  │                                                          │   │
│  │  Rate: Process within 5s of event, batch if needed       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Consolidation Scheduler                                  │   │
│  │                                                          │   │
│  │  Runs: Every 24h (configurable)                          │   │
│  │  Tasks: Cluster → Summarize → Supersede → Archive        │   │
│  │  Window: 3 AM local time (configurable)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ L1 Context Rebuilder                                     │   │
│  │                                                          │   │
│  │  Triggers: After consolidation, after compaction          │   │
│  │  Output: Cached user profile block for fast injection    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Health Monitor                                           │   │
│  │                                                          │   │
│  │  Checks: Provider health, queue depth, latency           │   │
│  │  Action: Trigger fallback if primary provider unhealthy  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 5.2 Extraction Queue Design

The extraction queue decouples message processing from memory storage, ensuring zero user-facing latency impact.

```python
class ExtractionQueue:
    """
    Async queue that processes conversation turns for memory extraction.
    Runs in the background, never blocks the response path.
    """

    def __init__(self, provider: MemoryProvider, config: dict):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._provider = provider
        self._batch_size = config.get("batch_size", 5)
        self._flush_interval = config.get("flush_interval_seconds", 5)
        self._running = False

    async def enqueue(self, turn: ConversationTurn):
        """
        Add a conversation turn to the extraction queue.
        Called from PostToolUse hook or after response delivery.
        Non-blocking — returns immediately.
        """
        # Run heuristic gate first (< 1ms)
        should_process, score = should_extract(
            turn.user_message,
            turn.recent_context
        )

        if not should_process:
            return  # Skip this turn entirely

        await self._queue.put(ExtractionJob(
            turn=turn,
            gate_score=score,
            enqueued_at=datetime.now()
        ))

    async def run(self):
        """Background loop that processes the queue."""
        self._running = True
        while self._running:
            batch = []

            # Collect up to batch_size items or wait for flush interval
            try:
                while len(batch) < self._batch_size:
                    job = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=self._flush_interval
                    )
                    batch.append(job)
            except asyncio.TimeoutError:
                pass  # Flush what we have

            if batch:
                await self._process_batch(batch)

    async def _process_batch(self, batch: list):
        """Extract and store memories from a batch of turns."""
        for job in batch:
            try:
                # Extract session notes using cheap LLM
                notes = await extract_session_notes(
                    job.turn.user_message,
                    job.turn.assistant_response,
                    job.turn.session_id
                )

                for note in notes:
                    # Supersession check against existing memories
                    similar = await self._provider.search(
                        query=note.content,
                        limit=10,
                        filters={"user_id": job.turn.user_id}
                    )

                    if similar:
                        actions = await self._provider.classify_update(
                            note.content, similar
                        )
                        await self._apply_actions(actions, note)
                    else:
                        # New fact, just add
                        await self._provider.add_session_note(
                            content=note.content,
                            session_id=job.turn.session_id,
                            importance=note.importance
                        )

                # Extract commitments if detected
                if has_commitment_language(job.turn.assistant_response):
                    await extract_and_store_commitments(
                        job.turn, self._provider
                    )

            except Exception as e:
                logger.warning(f"Extraction failed for turn: {e}")
                # Non-fatal — memory extraction failures should never
                # impact the user experience
```

#### 5.3 Where Pre-Extraction Happens

**Decision: Pre-extraction (heuristic gate) runs at enqueue time, NOT in the daemon.**

Rationale:
- The heuristic gate is < 1ms — cheaper to run inline than to queue and re-process
- Filtering before enqueue keeps the queue small
- The daemon only processes turns that passed the gate
- This prevents queue overflow during high-activity sessions

**The full extraction (LLM call) runs in the daemon:**
- This is the expensive operation (~$0.0005, ~200ms)
- Running it in the daemon ensures it never blocks response delivery
- Batch processing amortizes overhead

### 6. Auto-Recall (L2 → L1 Injection)

#### 6.1 When to Inject Memories

Every incoming user message triggers a fast L2 search to find relevant memories for context injection. This happens in the hot path but must complete within 200ms.

```python
async def auto_recall(
    user_message: str,
    user_id: str,
    conversation_context: list[str],
    max_memories: int = 5,
    max_tokens: int = 800
) -> str | None:
    """
    Search L2 for relevant memories and format for L1 injection.
    Called before LLM generation, within the hot path.

    Returns:
        Formatted memory block for system prompt injection, or None.
    """
    # 1. Check if this message likely needs memory context
    #    (topic shift, named entity, personal reference)
    needs_context = quick_context_check(user_message, conversation_context)
    if not needs_context:
        return None  # Simple continuation, no injection needed

    # 2. Fast L2 search
    results = await provider.search(
        query=user_message,
        filters={"user_id": user_id},
        limit=max_memories * 2  # Over-fetch, then filter
    )

    if not results:
        return None

    # 3. Filter by relevance threshold
    relevant = [r for r in results if r.score >= 0.6]
    if not relevant:
        return None

    # 4. Deduplicate against current conversation context
    novel = [r for r in relevant if not already_in_context(r, conversation_context)]
    if not novel:
        return None

    # 5. Format for injection (respecting token budget)
    block = format_memory_block(novel[:max_memories], max_tokens)
    return block
```

#### 6.2 Topic Continuity Detection

If the user's message is a clear continuation of the current topic, memory injection adds noise rather than value. Detect continuity via:

```python
def quick_context_check(message: str, recent_messages: list[str]) -> bool:
    """
    Should we search memory for this message?

    Returns False for clear continuations (no memory needed).
    Returns True for topic shifts, cold starts, or personal references.
    """
    # Cold start — always search
    if len(recent_messages) < 2:
        return True

    # Personal references — always search
    if has_personal_reference(message):
        return True

    # Named entities not in recent context — search
    entities = extract_entities_fast(message)
    recent_entities = extract_entities_fast(" ".join(recent_messages[-3:]))
    if entities - recent_entities:  # New entities
        return True

    # Topic shift detection (embedding similarity)
    recent_embedding = embed(recent_messages[-1])
    current_embedding = embed(message)
    similarity = cosine_similarity(recent_embedding, current_embedding)
    if similarity < 0.5:  # Significant topic shift
        return True

    return False  # Continuation of current topic
```

#### 6.3 ADHD-Specific Injection Rules

Memory injection must follow ADHD design principles:

| Rule | Implementation |
|------|---------------|
| Max 5 memories per injection | Hard limit in `auto_recall()` |
| Max 800 tokens per injection | Token budget in `format_memory_block()` |
| No guilt language | ADHD language filter applied to all injected content |
| Forward-facing framing | Commitments shown as opportunities, not obligations |
| One-thing-at-a-time | If task-focused, inject only task-relevant memories |
| Recency preference | Recent memories weighted higher in scoring |

### 7. Hook Integration

#### 7.1 Hook Wiring Summary

| Hook | Purpose | Timing |
|------|---------|--------|
| `PreToolUse` | Existing security hooks (unchanged) | Sync |
| `PostToolUse` | Trigger extraction queue for tool results | Async (fire-and-forget) |
| `PreCompact` | Checkpoint: flush queue, backup transcript, capture snapshot | Sync (fast) |
| `UserPromptSubmit` | Post-compaction context re-injection | Sync (fast) |
| `Stop` | Session-end: flush queue, trigger consolidation | Async |

#### 7.2 Hook Configuration

```python
# In tools/agent/hooks.py

from claude_agent_sdk import HookMatcher

MEMORY_HOOKS = {
    "PreCompact": [HookMatcher(hooks=[pre_compact_handler])],
    "UserPromptSubmit": [HookMatcher(hooks=[user_prompt_submit_handler])],
    "Stop": [HookMatcher(hooks=[session_end_handler])],
}

# Merge with existing security hooks
ALL_HOOKS = {**SECURITY_HOOKS, **MEMORY_HOOKS}
```

#### 7.3 Session End Handler

```python
async def session_end_handler(input_data):
    """
    Fires when the agent session ends (Stop hook).
    Final opportunity to persist session state.
    """
    # 1. Flush remaining extraction queue items
    await extraction_queue.flush()

    # 2. Capture final context snapshot
    await capture_context(
        user_id=get_current_user_id(),
        trigger="session_end",
        summary="Session ended"
    )

    # 3. Schedule consolidation if enough new memories accumulated
    new_count = await provider.count_session_notes(session_id)
    if new_count >= 10:
        schedule_consolidation(user_id, priority="normal")

    return {}
```

### 8. L1 Memory Block Format

The L1 memory block is the condensed context injected into the system prompt. It must be information-dense and ADHD-friendly.

**Format:**

```
[Memory Context]

User: Sam (energy: medium, last active: 2h ago)
Preferences: Prefers bullet points, dark mode, morning standups
Current project: DexAI Phase 11 (voice interface)

Recent relevant:
- Working on VoiceButton component integration (yesterday)
- Prefers Web Speech API over Whisper for cost reasons
- Has a meeting with Sarah about voice UX tomorrow at 10am

Active commitments:
- Send Sarah the voice UX mockups (due: tomorrow)
- Review PR #71 for audio processor changes (due: this week)
```

**Token budget allocation:**

| Section | Max Tokens | Content |
|---------|-----------|---------|
| User profile | 150 | Name, energy, preferences |
| Relevant memories | 500 | Top 3-5 from auto-recall |
| Active commitments | 200 | Due soon, ADHD-safe framing |
| Session state | 150 | Current task, last action |
| **Total** | **~1000** | |

---

## Implementation Plan

### Phase A: Foundation (3-4 days)

**Goal:** Heuristic gate + extraction queue + basic daemon

1. **Heuristic gate module** (`tools/memory/extraction/gate.py`)
   - Regex-based signal detection
   - Entity novelty scorer
   - Configurable threshold

2. **Extraction queue** (`tools/memory/extraction/queue.py`)
   - Async queue with batch processing
   - Integration with MemoryService
   - Non-blocking enqueue from hooks

3. **Session note extraction** (`tools/memory/extraction/extractor.py`)
   - LLM-based extraction prompt (Haiku)
   - Importance scoring
   - Structured output parsing

4. **Memory daemon** (`tools/memory/daemon.py`)
   - Background asyncio task
   - Extraction queue consumer
   - Health monitoring

5. **Hook integration** — Wire extraction queue to PostToolUse and Stop hooks

### Phase B: Compaction Integration (2-3 days)

**Goal:** Survive compaction without losing critical context

1. **PreCompact handler** — Transcript backup, queue flush, snapshot
2. **UserPromptSubmit handler** — Compaction detection + context re-injection
3. **Server-side compaction config** — Custom instructions, 80K threshold, pause support
4. **L1 memory block builder** — Condensed context formatting
5. **Compaction marker mechanism** — File-based flag for cross-hook communication

### Phase C: Supersession & Lifecycle (3-4 days)

**Goal:** Memories stay current and don't grow unboundedly

1. **Supersession classifier** — Haiku-based AUDN classification
2. **Provider interface extensions** — `supersede()`, `classify_update()`, `consolidate()`
3. **Native provider implementation** — SQL schema changes, supersession queries
4. **Consolidation scheduler** — Periodic clustering + summarization
5. **Cleanup scheduler** — Archive expired, delete stale snapshots

### Phase D: Auto-Recall & Polish (2-3 days)

**Goal:** Relevant memories appear in context automatically

1. **Auto-recall module** — L2 search + context injection
2. **Topic continuity detection** — Embedding-based shift detection
3. **ADHD-safe formatting** — Language filter, token budgets, one-thing-at-a-time
4. **Configuration** — `args/memory.yaml` updates for new settings
5. **Dashboard integration** — Memory activity feed, consolidation status

**Total estimated: 10-14 days**

---

## Configuration

### New Settings (additions to `args/memory.yaml`)

```yaml
# =============================================================================
# Extraction Pipeline
# =============================================================================
extraction:
  # Heuristic gate threshold (0.0-1.0)
  # Lower = more memories extracted, higher cost
  # Higher = fewer memories, lower cost
  gate_threshold: 0.3

  # Model for extraction (cheapest available)
  extraction_model: "claude-haiku-4-5-20251001"

  # Batch size for queue processing
  batch_size: 5

  # Seconds before flushing partial batch
  flush_interval_seconds: 5

  # Max queue depth (prevent unbounded growth)
  max_queue_size: 1000

# =============================================================================
# Compaction Strategy
# =============================================================================
compaction:
  # Token threshold for proactive compaction (% of context limit)
  proactive_threshold_pct: 60

  # Custom compaction instructions
  instructions: >
    Preserve: current task state, user preferences, active commitments,
    key technical decisions, file paths being edited.
    Discard: routine greetings, tool output details, intermediate reasoning.

  # Use server-side compaction with pause (when controlling API loop)
  use_server_side: true
  server_side_trigger_tokens: 80000
  pause_after_compaction: true

  # Topic shift detection threshold (embedding similarity)
  topic_shift_threshold: 0.4

# =============================================================================
# Auto-Recall (L2 → L1 injection)
# =============================================================================
auto_recall:
  enabled: true

  # Max memories to inject per turn
  max_memories: 5

  # Max tokens for memory block
  max_tokens: 800

  # Relevance threshold for injection
  relevance_threshold: 0.6

  # Skip injection if conversation is a clear continuation
  skip_on_continuation: true

# =============================================================================
# Consolidation (L2 → L3 promotion)
# =============================================================================
consolidation:
  enabled: true

  # Run every N hours
  interval_hours: 24

  # Preferred hour for consolidation (24h format)
  preferred_hour: 3

  # Min cluster size for consolidation
  min_cluster_size: 3

  # Similarity threshold for clustering
  cluster_similarity: 0.85

  # Min age before eligible for consolidation (days)
  min_age_days: 7

  # Model for consolidation summaries
  consolidation_model: "claude-haiku-4-5-20251001"

# =============================================================================
# Supersession
# =============================================================================
supersession:
  enabled: true

  # Number of similar memories to check against
  comparison_top_k: 10

  # Model for classification
  classification_model: "claude-haiku-4-5-20251001"

  # Archive superseded memories (vs hard delete)
  archive_superseded: true
```

---

## Alignment with Memory Providers

### How Each Provider Handles the Lifecycle

| Capability | Native | Mem0 | Zep |
|-----------|--------|------|-----|
| **Extraction** | DexAI heuristic gate + Haiku | `memory.add(infer=True)` handles extraction | `thread.add_messages()` + automatic graph ingestion |
| **Supersession** | DexAI classifier + SQL updates | Built-in AUDN pipeline (ADD/UPDATE/DELETE/NOOP) | Temporal invalidation (`valid_at` / `invalid_at`) |
| **Consolidation** | DexAI daemon + Haiku summarizer | Not built-in (use `memory.add()` with cluster content) | Graph naturally consolidates via entity resolution |
| **Search** | BM25 + cosine similarity | Vector + metadata + optional reranker (RRF, Cohere) | Full-text + semantic + graph traversal (RRF, MMR) |
| **L1 building** | DexAI search + format | DexAI `memory.search()` + format | `thread.get_user_context()` (<200ms native) |
| **Archival** | SQL `archived=True` flag | Memory history audit trail | `invalid_at` timestamp (never truly deleted) |
| **Cost** | Embedding API only (~$0.0001/search) | Included in Mem0 pricing | Included in Zep pricing |

### Provider Selection Guidance

| Scenario | Recommended Provider | Reason |
|----------|---------------------|--------|
| Self-hosted, no external deps | Native | Zero cost, full control |
| Best accuracy, managed service | Zep Cloud | Temporal knowledge graph, <200ms |
| Graph relationships matter | Mem0 (with `enable_graph=True`) | Entity + relationship tracking |
| Budget-constrained | Native | Only embedding API costs |
| Enterprise compliance | Zep BYOC / Native | Data stays in your infrastructure |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Extraction queue grows unbounded | Low | Medium | Max queue size (1000), discard oldest on overflow |
| LLM extraction produces poor results | Medium | Low | Heuristic gate filters noise; supersession fixes errors over time |
| Compaction loses critical context | High | High | PreCompact backup, L1 re-injection, external memory persistence |
| PostCompact hook never added to SDK | Medium | Medium | UserPromptSubmit workaround + server-side pause_after_compaction |
| Consolidation merges distinct concepts | Low | Medium | High similarity threshold (0.85), LLM-generated summaries |
| Memory injection distracts the model | Medium | Medium | Relevance threshold (0.6), ADHD token budgets, continuity skip |
| Provider failover loses recent memories | Low | High | Extraction queue persists to disk; fallback to native |
| Background daemon crashes | Low | Medium | Watchdog restart, health monitoring, graceful degradation |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Memory extraction latency (user-facing) | 0ms | Async queue — user never waits |
| Auto-recall search latency | <200ms | Time from message receipt to L1 injection |
| Context survival after compaction | >90% of key facts preserved | Compare pre/post compaction memory coverage |
| Memory deduplication rate | >80% of duplicates caught | Count NOOP/UPDATE vs ADD actions |
| Consolidation compression ratio | 3:1 or better | L2 entries consolidated into L3 |
| False positive injection rate | <10% | Irrelevant memories injected into context |
| User-perceived relevance | >80% useful | Sampling of injected memories rated by relevance |
| Daemon uptime | >99.9% | Health monitor tracking |

---

## References

### Research Papers
- SimpleMem: Efficient Lifelong Memory for LLM Agents (arXiv 2601.02553, Jan 2026)
- MemGPT: Towards LLMs as Operating Systems (arXiv 2310.08560, Oct 2023)
- Sleep-Time Compute (arXiv 2504.13171, Apr 2025)
- H-MEM: Hierarchical Memory (arXiv 2507.22925, Jul 2025)
- Mem0: Production-Ready AI Agents with Scalable Long-Term Memory (arXiv 2504.19413, Apr 2025)
- Generative Agents: Interactive Simulacra (arXiv 2304.03442, Apr 2023)
- FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory
- LoCoMo: Evaluating Very Long-Term Conversational Memory (arXiv 2402.17753)

### Claude SDK Documentation
- [Agent SDK Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) — PreCompact, PostToolUse, UserPromptSubmit
- [Context Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) — Server-side compaction with `pause_after_compaction`
- [Automatic Context Compaction Cookbook](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction)
- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — External artifacts pattern

### Provider Documentation
- [Mem0 API Docs](https://docs.mem0.ai/) — AUDN pipeline, graph memory
- [Zep Documentation](https://help.getzep.com/) — Temporal knowledge graph, thread context
- [Letta/MemGPT Docs](https://docs.letta.com/concepts/memgpt/) — Tiered memory, sleep-time agents
- [OpenAI Agents SDK Context Personalization](https://cookbook.openai.com/examples/agents_sdk/context_personalization) — Session notes pattern

### Community Resources
- [GitHub Issue #14258](https://github.com/anthropics/claude-code/issues/14258) — PostCompact hook request (workarounds documented)
- [JetBrains: Efficient Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) — Observation masking vs summarization
- [A 2026 Memory Stack for Enterprise Agents](https://alok-mishra.com/2026/01/07/a-2026-memory-stack-for-enterprise-agents/)
- [ICLR 2026 MemAgents Workshop](https://openreview.net/forum?id=U51WxL382H)

---

*This design document should be updated as the Claude Agent SDK adds PostCompact hooks or other compaction-related capabilities.*
