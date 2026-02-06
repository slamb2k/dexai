# Subagent Model Selection Guide (v2)

## How It Works

Agent SDK subagents specify model as: `sonnet` | `opus` | `haiku` | `inherit`

These resolve via environment variables set in `ClaudeAgentOptions.env`:

| Alias | Resolves via | Default |
|---|---|---|
| `sonnet` | `ANTHROPIC_DEFAULT_SONNET_MODEL` | `claude-sonnet-4-5` |
| `opus` | `ANTHROPIC_DEFAULT_OPUS_MODEL` | `claude-opus-4-5` |
| `haiku` | `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `claude-haiku-4-5` |
| `inherit` | Parent model | (whatever the parent uses) |

Since **all traffic routes through OpenRouter**, these env vars contain OpenRouter model IDs (e.g., `anthropic/claude-sonnet-4-5`). OpenRouter's Anthropic Skin handles prompt caching, extended thinking, and beta features transparently.

## Complexity-Proportional Remapping (Default Strategy)

| Parent Complexity | `sonnet` → | `opus` → | `haiku` → |
|---|---|---|---|
| CRITICAL | Sonnet 4.5 | Opus 4.5 | Haiku 4.5 |
| HIGH | Sonnet 4.5 | Sonnet 4.5 | Haiku 4.5 |
| MODERATE | Sonnet 4.5 | Sonnet 4.5 | Haiku 4.5 |
| LOW | **Haiku 4.5** | Sonnet 4.5 | Haiku 4.5 |
| TRIVIAL | **Haiku 4.5** | **Haiku 4.5** | Haiku 4.5 |

The key insight: **if the parent task is simple, subagent work is almost certainly simple too.** A TRIVIAL parent spawning subagents marked `sonnet` doesn't need actual Sonnet — Haiku handles it fine at 4x lower cost.

## Alias Semantics

Think of aliases as relative capability requests, not absolute model preferences:

- **`sonnet`** = "I need reasonable capability" → Downgrades to Haiku for simple parent tasks
- **`opus`** = "Don't downgrade me" → Stays at Sonnet+ even for LOW complexity. Use for safety-critical subagents (code review, compliance checks)
- **`haiku`** = "I'm efficient work" → Always Haiku regardless of parent complexity
- **`inherit`** = "Match the parent" → Already complexity-appropriate since the parent was routed

## Subagent Cost Impact

Without intervention, subagents silently multiply your costs:

```
Parent: Sonnet ($3/M input) + 3 subagents marked 'sonnet' = 4× Sonnet pricing
→ $12/M input tokens for what might be a simple task

With complexity-proportional routing (TRIVIAL parent):
Parent: Haiku ($0.80/M) + 3 subagents 'sonnet'→Haiku = 4× Haiku pricing  
→ $3.20/M input tokens — 73% savings
```

## Environment Variables Reference

| Variable | Purpose | Set by |
|---|---|---|
| `ANTHROPIC_BASE_URL` | OpenRouter endpoint | `build_options()` |
| `ANTHROPIC_AUTH_TOKEN` | OpenRouter API key | `build_options()` |
| `ANTHROPIC_API_KEY` | Must be `""` for OpenRouter | `build_options()` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | What `sonnet` resolves to | `SubagentStrategy` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | What `opus` resolves to | `SubagentStrategy` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | What `haiku` resolves to | `SubagentStrategy` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | Override ALL subagent aliases | `SubagentStrategy` (optional) |
| `DISABLE_PROMPT_CACHING` | Set `"1"` for non-Anthropic models | `build_options()` |

## Recommendations

1. **Start with `ANTHROPIC_ONLY` profile** — simplest, most reliable
2. **Use `inherit` generously** — if a subagent doesn't have a strong model opinion, let it inherit the parent's (already complexity-appropriate) model
3. **Reserve `opus` for safety-critical subagents** — code review, data validation, compliance checks
4. **Monitor with `get_stats()` first** — understand your complexity distribution before optimising
5. **Use Exacto for tool-heavy parent tasks** — subagents inherit the OpenRouter transport, but Exacto is a parent model property. If your parent spawns many tool-using subagents, consider making the parent Exacto too
6. **Trust OpenRouter for failover** — even if a subagent's resolved model has a provider outage, OpenRouter fails over to another provider automatically
