"""DexAI Model Routing Framework - OpenRouter-first model routing with complexity-based selection."""

from .model_router import (
    ModelRouter,
    ModelSpec,
    ModelTier,
    RoutingProfile,
    RoutingDecision,
    TaskComplexity,
    ComplexitySignals,
    SubagentStrategy,
    ObservabilityConfig,
    classify_complexity,
    routed_query,
    setup_langfuse_tracing,
    MODELS,
    SUBAGENT_STRATEGIES,
    ROUTING_CONFIG_PATH,
)

__all__ = [
    "ModelRouter",
    "ModelSpec",
    "ModelTier",
    "RoutingProfile",
    "RoutingDecision",
    "TaskComplexity",
    "ComplexitySignals",
    "SubagentStrategy",
    "ObservabilityConfig",
    "classify_complexity",
    "routed_query",
    "setup_langfuse_tracing",
    "MODELS",
    "SUBAGENT_STRATEGIES",
    "ROUTING_CONFIG_PATH",
]
