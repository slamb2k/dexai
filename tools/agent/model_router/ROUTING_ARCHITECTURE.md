# openclaw Routing Architecture: OpenRouter-First Design

## Executive Summary

**Recommendation: Route ALL traffic through OpenRouter, including Anthropic models. Do not use Claude Code Router (CCR). Use a thin local routing layer only for domain-specific decisions that OpenRouter cannot make (task complexity classification and subagent alias remapping). Add Langfuse for application-level tracing.**

The architecture:

```
Your App
  → Local Router (complexity classification + subagent alias mapping only)
  → ClaudeAgentOptions.env (model ID + env vars)
  → Agent SDK
  → OpenRouter (Anthropic Skin) [transport, failover, billing, Exacto]
  → Provider (Anthropic / OpenAI / Google / etc.)

Observability:
  Langfuse (OTEL)  ← traces every Agent SDK call automatically
  OpenRouter Dashboard ← cost, usage, model distribution
```

---

## Question-by-Question Analysis

### 1. What should OpenRouter handle vs the local router?

**Let OpenRouter handle:**

| Capability | Why OpenRouter is better |
|---|---|
| **Provider failover** | Real-time health monitoring across all providers. If Anthropic is rate-limiting, OpenRouter seamlessly fails over to another Anthropic provider. You can't replicate this locally — you don't have visibility into provider health. |
| **Provider selection for a given model** | Multiple providers host the same model (e.g., several host Claude Sonnet). OpenRouter load-balances across them weighted by price, health, and throughput. |
| **Tool-calling quality (Exacto)** | OpenRouter sees billions of requests/month. Their Exacto variant restricts routing to providers with demonstrably better tool-use accuracy based on real-world telemetry. This is invaluable for agentic workloads and is impossible to replicate locally. |
| **Billing consolidation** | Single API key, single credit balance, per-key spending limits, team budgets. |
| **Model fallbacks** | The `models` array lets you specify priority-ordered fallbacks (e.g., try Sonnet 4.5, fall back to GPT-4o if it errors). OpenRouter handles this transparently. |
| **Throughput/latency optimisation** | `:nitro` suffix prioritises throughput, `:floor` prioritises price. These leverage OpenRouter's real-time provider performance data. |
| **Auto model selection** | `openrouter/auto` delegates model selection entirely to OpenRouter's classifier. Useful as a baseline or for unpredictable workloads. |
| **Prompt caching** | For Anthropic models, OpenRouter automatically enables prompt caching and extended context via the Anthropic Skin. No configuration needed. |

**Keep locally (in your Python router):**

| Capability | Why this must be local |
|---|---|
| **Task complexity classification** | Only you know your domain. "Analyse our donor pipeline" is HIGH complexity for your app but OpenRouter has zero context about what that means. Your heuristics (or a lightweight Haiku pre-classification call) encode domain knowledge. |
| **Subagent alias remapping** | The Agent SDK's `sonnet`/`opus`/`haiku`/`inherit` aliases resolve via environment variables. Only your router knows that for a TRIVIAL parent task, `sonnet` should downgrade to Haiku. This is per-query, domain-aware logic. |
| **Budget policy enforcement** | "Never spend more than $X per session" or "cap subagent cost at Haiku-tier" — these are business rules, not transport concerns. |
| **Model selection (which model for which complexity)** | The routing table mapping CRITICAL→Opus, HIGH→Sonnet+Exacto, etc. is your domain policy. OpenRouter's Auto Router doesn't know your cost/quality tradeoff preferences. |

**The principle: OpenRouter handles transport-layer intelligence (failover, provider quality, billing). Your local router handles application-layer intelligence (task semantics, business rules, subagent strategies).**

---

### 2. One routing layer or both?

**Use both, but with clearly separated responsibilities.**

- **OpenRouter-only** (no local logic): Works fine if you always use the same model for everything, or if you're happy delegating model selection entirely to OpenRouter's Auto Router. Simplest possible setup — just set the 3 env vars and go.

- **Local router + OpenRouter** (recommended): Your local router picks the model ID and configures subagent aliases based on task complexity. OpenRouter then handles actually delivering the request to the best provider for that model. There is zero performance penalty from this approach because the local router does no proxying — it just sets environment variables that the Agent SDK passes to OpenRouter. The local "routing" is purely a configuration step before the API call, not an additional network hop.

- **Local proxy (CCR) + OpenRouter**: This is the pattern to avoid. CCR runs a local HTTP server on port 3456, which adds an actual network hop: App → localhost:3456 → OpenRouter → Provider. See the CCR section below for why this is problematic.

```
RECOMMENDED: Local router sets env vars, OpenRouter handles transport
┌──────────────┐    env vars    ┌───────────┐    HTTPS    ┌─────────────┐
│ Local Router │ ─────────────→ │ Agent SDK │ ──────────→ │ OpenRouter  │
│ (Python)     │  (no network)  │           │             │ → Provider  │
└──────────────┘                └───────────┘             └─────────────┘

AVOID: Local proxy adds network hop
┌──────────────┐    HTTPS     ┌──────────┐    HTTPS    ┌─────────────┐
│ Agent SDK    │ ───────────→ │ CCR      │ ──────────→ │ OpenRouter  │
│              │  localhost    │ :3456    │             │ → Provider  │
└──────────────┘              └──────────┘             └─────────────┘
```

---

### 3. Should Anthropic models also go through OpenRouter?

**Yes. Route everything through OpenRouter, including Anthropic models.**

The reasons to go direct to Anthropic would be:
- **Prompt caching**: OpenRouter's Anthropic Skin automatically enables prompt caching for Anthropic models. No loss here.
- **Extended thinking**: Anthropic Skin passes through thinking blocks natively. No loss.
- **Beta features**: OpenRouter passes through `x-anthropic-beta` headers. Supported.
- **Latency**: OpenRouter adds ~25ms at the edge, ~40ms under typical production conditions (their published figures). For agentic workloads where individual LLM calls take 2-30+ seconds, this is negligible.

The reasons to go through OpenRouter are much stronger:
- **Automatic failover**: If Anthropic's primary endpoint is rate-limiting you, OpenRouter routes to another Anthropic provider transparently. This alone justifies the overhead.
- **Unified billing**: One credit balance for all models, all providers.
- **Exacto**: For tool-heavy agentic workloads (which is exactly what Agent SDK produces), Exacto routes to providers with better tool-calling accuracy. Different providers hosting the same Anthropic model can vary in tool-use accuracy due to inference implementation details. Exacto eliminates this variance.
- **Observability**: All traffic through one gateway means one dashboard for cost/usage/model distribution.
- **BYOK option**: If you later want to use your own Anthropic API key for volume discounts while keeping OpenRouter's routing, BYOK lets you do that.

**The only scenario where direct Anthropic makes sense**: You have a compliance requirement that prohibits third-party proxies, or you need guaranteed < 50ms first-token latency. Neither applies to openclaw.

---

### 4. Should you use Claude Code Router (CCR)?

**No. Use OpenRouter directly via the Anthropic Skin.**

CCR was created to solve a specific problem: using non-Anthropic models with Claude Code's CLI when you didn't have an Anthropic account. It works by running a local HTTP proxy that intercepts Anthropic API calls and transforms them for other providers.

For your use case (Agent SDK with OpenRouter), CCR is the wrong tool:

**CCR adds complexity without benefit:**
- CCR runs a local Node.js HTTP server that must be started (`ccr start`) and managed as a service. This is an operational dependency that can crash, has connection issues (evidenced by the GitHub issues), and needs updating separately.
- OpenRouter's Anthropic Skin already speaks the Anthropic Messages API natively. The Agent SDK connects directly to OpenRouter with just 3 environment variables. No proxy needed.
- CCR's `openrouter` transformer does what OpenRouter already does natively — it's a proxy for a proxy.

**CCR's transformer architecture is designed for direct provider connections:**
- The `tooluse` transformer (for DeepSeek direct API) and `enhancetool` transformer exist because those providers' raw APIs don't perfectly match Claude Code's expectations.
- OpenRouter already handles this normalisation at the cloud level. When you send `anthropic/claude-sonnet-4-5` through OpenRouter, the Anthropic Skin handles all protocol translation.
- For non-Anthropic models (e.g., `openai/gpt-4o`), OpenRouter also handles the OpenAI→Anthropic protocol mapping.

**Summary: CCR solves problems that OpenRouter's Anthropic Skin already solves, while adding a local process, network hop, and operational overhead.**

---

### 5. Challenges with CCR and enhancetool

The `enhancetool` transformer is CCR's mechanism for improving tool-call reliability with models that produce malformed tool-use parameters. Here's why it's problematic:

**enhancetool disables streaming for tool calls.** The CCR docs explicitly state: "this will cause the tool call information to no longer be streamed." In an Agent SDK context where tool calls are the primary interaction pattern (file edits, shell commands, MCP calls), this means:
- Every tool call is fully buffered before the response starts arriving
- The user sees nothing until the entire tool response is complete
- For long-running tool chains, this creates significant perceived latency
- Agent SDK's streaming architecture is undermined

**enhancetool is a workaround for provider-level problems that Exacto solves better.** The reason tool calls are malformed is because some providers' inference implementations produce slightly wrong JSON schemas. CCR's approach: buffer the response, attempt to fix the JSON locally. OpenRouter's approach (Exacto): don't route to those providers in the first place. Exacto uses real-world telemetry from billions of requests to identify which providers have better tool-calling accuracy, and only routes to those. Prevention > cure.

**enhancetool's error tolerance is heuristic.** It tries to fix malformed tool parameters, but there's no guarantee it will handle every edge case. Exacto, by contrast, avoids the problem entirely by selecting providers with demonstrated accuracy.

**Using OpenRouter directly (no CCR, no enhancetool) provides:**
- Full streaming for all responses including tool calls
- Exacto-grade tool-calling quality without buffering
- No local Node.js process to manage
- Fewer failure modes

---

### 6. Will using both local router and OpenRouter degrade performance?

**No — because the local router isn't a proxy.**

This is the key distinction. There are two ways to combine local logic with a cloud router:

**Pattern A (our approach): Local logic sets configuration, OpenRouter handles transport.**
The local `ModelRouter` class runs classify_complexity(), looks up the routing table, and sets environment variables in `ClaudeAgentOptions.env`. This is pure Python dict manipulation — no network call, no HTTP server, no latency. The Agent SDK then makes a single HTTPS call to OpenRouter. Total network hops: 1 (same as using OpenRouter alone).

**Pattern B (CCR approach): Local proxy intercepts and forwards.**
CCR runs an HTTP server on localhost:3456. The Agent SDK sends to localhost:3456, CCR processes and forwards to OpenRouter, OpenRouter forwards to the provider. Total network hops: 2. The localhost hop is fast (~1ms) but adds: process management overhead, potential connection errors, buffering for transforms, and a debugging blind spot.

**Our architecture has zero additional latency over plain OpenRouter** because the "routing" happens before the API call as configuration, not during it as proxying. The only latency is OpenRouter's own ~25-40ms overhead, which is the same whether you use a local router or not.

---

### 7. Observability Recommendations

Three complementary layers, each capturing different information:

#### Layer 1: OpenRouter Dashboard (free, built-in)
**What it captures:** Cost per request, model distribution, provider used, usage over time.
**Setup:** Nothing — you get this automatically with your OpenRouter account.
**Best for:** Quick cost checks, verifying routing decisions, team spending oversight.
**Limitation:** No application-level context (you can't see "this was a CRITICAL complexity task" or trace through subagent chains).

#### Layer 2: Langfuse (recommended for application-level tracing)
**What it captures:** Full request/response traces with nested spans for every Agent SDK call, tool invocation, and subagent. Token usage, latency per span, cost tracking (can ingest OpenRouter cost data directly). Session management, user tracking, evaluation pipelines.
**Setup:** `pip install langfuse "langsmith[claude-agent-sdk]" "langsmith[otel]"`, then call `configure_claude_agent_sdk()` once at startup. Every Agent SDK query is automatically instrumented via OpenTelemetry.
**Best for:** Debugging why a specific query failed, understanding subagent chains, evaluating response quality, identifying which complexity levels produce the best results.
**Cost:** Generous free tier (50k observations/month on cloud), or self-host for free.
**Key advantage:** First-class Claude Agent SDK integration via LangSmith's OTEL bridge. Every tool call, model completion, and subagent invocation appears as a nested span automatically.

#### Layer 3: Helicone (optional, for gateway-level observability)
**What it captures:** Similar to OpenRouter's dashboard but with richer analytics: per-user tracking, latency distributions, cost breakdowns, request/response logging, caching analytics.
**Setup:** Change your base URL from `https://openrouter.ai/api` to `https://openrouter.helicone.ai/api` and add a `Helicone-Auth` header.
**Best for:** When you need more detailed analytics than OpenRouter's dashboard provides, especially per-user cost tracking and latency percentiles.
**Cost:** Free tier (10k requests/month), paid plans for more.
**Trade-off:** Adds another proxy hop (App → Helicone → OpenRouter → Provider), adding a few ms of latency. Also, Helicone's OpenRouter integration is documented as "maintained but no longer actively developed" — Helicone prefers you use their own AI Gateway directly. For OpenRouter users, Langfuse is the more natural fit.

#### Recommended stack:
```
Production: OpenRouter Dashboard + Langfuse
  - OpenRouter for cost/billing visibility
  - Langfuse for application-level tracing and debugging

Optional addition: Helicone
  - Only if you need per-user cost tracking beyond what OpenRouter provides
  - Or if you want request-level caching analytics
```

---

## Revised Architecture Decision Record

### Context
Building an AI assistant (openclaw) using Claude Agent SDK that needs multi-model support, cost optimisation, and observability.

### Decision
1. **Transport: OpenRouter exclusively** — all models, all providers, including Anthropic
2. **Local router: configuration only** — complexity classification, routing table lookup, subagent alias remapping, budget policy
3. **No local proxy** — no CCR, no localhost HTTP server
4. **Observability: Langfuse + OpenRouter Dashboard** — Helicone optional

### Consequences
- Single API key for all providers
- ~25-40ms latency overhead (acceptable for agentic workloads)
- Automatic failover for all providers
- Exacto available for tool-calling quality
- Prompt caching preserved for Anthropic models
- Full streaming preserved (no enhancetool buffering)
- Zero additional latency from local routing (configuration-only, no proxy)
- Langfuse traces every Agent SDK interaction automatically

### Rejected alternatives
- **Direct Anthropic for Claude models**: Loses failover, Exacto, unified billing. Gains ~25ms latency reduction (not meaningful for multi-second agentic calls).
- **CCR**: Solves problems OpenRouter already solves, adds operational overhead, enhancetool breaks streaming.
- **LiteLLM self-hosted**: Maximum control but high operational burden. Only justified for strict data residency requirements.
- **Helicone AI Gateway (replacing OpenRouter)**: Strong observability but less model coverage and community ecosystem than OpenRouter for Agent SDK.
