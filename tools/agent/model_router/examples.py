"""
openclaw Routing Examples (v2)
===============================
All examples route through OpenRouter. No local proxy, no CCR.

Prerequisites:
    export OPENROUTER_API_KEY="sk-or-v1-..."

    # Optional: Langfuse for application-level tracing
    export LANGFUSE_PUBLIC_KEY="pk-lf-..."
    export LANGFUSE_SECRET_KEY="sk-lf-..."
    export LANGFUSE_BASE_URL="https://cloud.langfuse.com"

    pip install claude-agent-sdk
    pip install langfuse "langsmith[claude-agent-sdk]" "langsmith[otel]"  # optional
"""

import asyncio
from claude_agent_sdk import ClaudeSDKClient

from model_router import (
    ModelRouter,
    RoutingProfile,
    TaskComplexity,
    SubagentStrategy,
    SUBAGENT_STRATEGIES,
    routed_query,
)


# ---------------------------------------------------------------------------
# Example 1: Simplest possible usage
# ---------------------------------------------------------------------------

async def example_basic():
    """
    Automatic complexity detection → model selection → OpenRouter.
    This is the recommended starting point.
    """
    router = ModelRouter(profile=RoutingProfile.ANTHROPIC_ONLY)

    async for msg in routed_query(
        "What CRM features should we prioritise for Q3?",
        router,
        system_prompt="You are an AI assistant for a Dynamics 365 partner.",
    ):
        for block in msg.content:
            if hasattr(block, "text"):
                print(block.text)


# ---------------------------------------------------------------------------
# Example 2: Exacto for tool-heavy workloads
# ---------------------------------------------------------------------------

async def example_exacto():
    """
    Force Exacto variant for a query with many tools.

    Exacto routes to OpenRouter providers with the best tool-calling
    accuracy based on real-world telemetry from billions of requests.
    No streaming penalty (unlike CCR's enhancetool).
    """
    router = ModelRouter(profile=RoutingProfile.QUALITY_FIRST)

    decision = router.route(
        "Search our donor database, cross-reference with recent events, "
        "then draft personalised outreach emails for the top 10 prospects.",
        use_exacto=True,  # Force Exacto regardless of routing table
    )

    print(f"Model: {decision.primary_model.routed_id}")
    # → "anthropic/claude-sonnet-4-5:exacto"

    options = router.build_options(
        decision,
        system_prompt="You are a donor intelligence assistant.",
        allowed_tools=[
            "mcp__crm__search_donors",
            "mcp__crm__get_events",
            "mcp__email__draft",
        ],
    )

    async for msg in routed_query(
        "Find donors who attended our gala but haven't donated in 6 months.",
        router,
        use_exacto=True,
    ):
        for block in msg.content:
            if hasattr(block, "text"):
                print(block.text)


# ---------------------------------------------------------------------------
# Example 3: Auto Router — delegate everything to OpenRouter
# ---------------------------------------------------------------------------

async def example_auto_router():
    """
    Let OpenRouter's classifier pick the model.

    Good for: prototyping, unpredictable workloads, evaluating whether
    your local complexity heuristics add value over OpenRouter's built-in.
    You can restrict the model pool with OpenRouter plugins (anthropic/*).
    """
    router = ModelRouter(profile=RoutingProfile.AUTO_ROUTER)

    decision = router.route("Explain quantum entanglement simply.")
    print(f"Model: {decision.primary_model.routed_id}")
    # → "openrouter/auto" — OpenRouter decides the actual model

    options = router.build_options(decision)
    # The Agent SDK sends to OpenRouter, which picks the best model


# ---------------------------------------------------------------------------
# Example 4: Multi-turn conversation with Langfuse tracing
# ---------------------------------------------------------------------------

async def example_langfuse_traced():
    """
    Every query, tool call, and subagent invocation is automatically
    captured as an OpenTelemetry span in Langfuse.

    Requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in env.
    View traces at https://cloud.langfuse.com
    """
    # Langfuse tracing is configured automatically in ModelRouter.__init__
    # when LANGFUSE_PUBLIC_KEY is detected in environment.
    router = ModelRouter(profile=RoutingProfile.BALANCED)

    # Optionally wrap with Langfuse context for extra metadata
    try:
        from langfuse import get_client, propagate_attributes
        langfuse = get_client()

        with langfuse.start_as_current_observation(
            as_type="span", name="openclaw-session"
        ):
            with propagate_attributes(
                user_id="user_123",
                session_id="session_abc",
                metadata={"profile": "balanced", "version": "2.0"},
            ):
                async for msg in routed_query(
                    "Analyse our pipeline conversion rates.",
                    router,
                    system_prompt="You are a CRM analytics assistant.",
                ):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            print(block.text)

        langfuse.flush()
    except ImportError:
        # Works fine without Langfuse — just no tracing
        async for msg in routed_query(
            "Analyse our pipeline conversion rates.",
            router,
        ):
            for block in msg.content:
                if hasattr(block, "text"):
                    print(block.text)


# ---------------------------------------------------------------------------
# Example 5: Explicit complexity override
# ---------------------------------------------------------------------------

async def example_explicit_complexity():
    """
    When you know the task complexity better than the heuristic.

    The heuristic might classify "update the donor record" as LOW,
    but you know this donor has complex compliance requirements.
    """
    router = ModelRouter(profile=RoutingProfile.ANTHROPIC_ONLY)

    async for msg in routed_query(
        "Update the donor record for Organisation XYZ.",
        router,
        explicit_complexity=TaskComplexity.HIGH,  # Override heuristic
        system_prompt="You are a CRM assistant.",
    ):
        for block in msg.content:
            if hasattr(block, "text"):
                print(block.text)


# ---------------------------------------------------------------------------
# Example 6: Cost-optimised with budget cap
# ---------------------------------------------------------------------------

async def example_cost_optimised():
    """
    Aggressive cost optimisation with a per-session budget cap.
    """
    router = ModelRouter(
        profile=RoutingProfile.COST_OPTIMISED,
        max_budget_usd=0.50,  # Hard cap
    )

    queries = [
        "Format this JSON.",                          # → TRIVIAL → DeepSeek V3
        "Summarise this meeting transcript.",          # → LOW → GPT-4o Mini
        "Compare these two API approaches.",           # → MODERATE → GPT-4o Mini
        "Design a migration strategy for our CRM.",   # → HIGH → GPT-4o
    ]

    for q in queries:
        decision = router.route(q)
        print(f"  {q[:50]}... → {decision.primary_model.display_name}")

    print(f"\nStats: {router.get_stats()}")


# ---------------------------------------------------------------------------
# Example 7: Custom routing table
# ---------------------------------------------------------------------------

async def example_custom_routing():
    """
    Define your own routing table mapping complexity → model.
    """
    router = ModelRouter(
        profile=RoutingProfile.BALANCED,  # Ignored when custom table provided
        custom_routing_table={
            TaskComplexity.CRITICAL: "claude-opus-4.5",
            TaskComplexity.HIGH:     "claude-sonnet-4.5-exacto",
            TaskComplexity.MODERATE: "gemini-2.5-pro",      # Gemini for mid-tier
            TaskComplexity.LOW:      "gpt-4o-mini",
            TaskComplexity.TRIVIAL:  "deepseek-v3",
        },
    )

    decision = router.route("Compare React vs Vue for our dashboard.")
    print(f"Custom routing → {decision.primary_model.display_name}")


# ---------------------------------------------------------------------------
# Example 8: Observability stats
# ---------------------------------------------------------------------------

async def example_stats():
    """
    Check routing distribution to inform optimisation decisions.

    Run for a period with ANTHROPIC_ONLY, then examine stats:
    - If 80%+ queries are TRIVIAL/LOW → switch to COST_OPTIMISED
    - If Exacto queries are >50% → your workload is tool-heavy, good
    - If model distribution is 90% one model → consider Auto Router
    """
    router = ModelRouter(profile=RoutingProfile.BALANCED)

    test_prompts = [
        "Hi",
        "What's our Q3 revenue?",
        "Compare these two vendor proposals and recommend one.",
        "Design a multi-step automation for donor onboarding.",
        "Format this CSV.",
    ]

    for prompt in test_prompts:
        router.route(prompt)

    stats = router.get_stats()
    print(f"Total queries: {stats['total_queries']}")
    print(f"Model distribution: {stats['model_distribution']}")
    print(f"Complexity distribution: {stats['complexity_distribution']}")
    print(f"Exacto queries: {stats['exacto_queries']}")


# ---------------------------------------------------------------------------
# Run all examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Example 6: Cost-Optimised Routing")
    print("=" * 60)
    asyncio.run(example_cost_optimised())

    print("\n" + "=" * 60)
    print("Example 8: Routing Stats")
    print("=" * 60)
    asyncio.run(example_stats())
