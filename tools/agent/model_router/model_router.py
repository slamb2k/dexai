"""
DexAI Model Routing Framework
==============================
OpenRouter-first architecture for intelligent model selection.

Architecture:
    App -> ModelRouter (configuration only, no proxy)
        -> Options dict (model ID + env vars)
        -> Agent SDK -> OpenRouter (Anthropic Skin) -> Provider

    Observability:
        Langfuse (OTEL) traces every Agent SDK call automatically
        OpenRouter Dashboard provides cost/usage/model distribution

Design principles:
    1. OpenRouter is the ONLY transport layer (even for Anthropic models)
    2. Local routing = configuration decisions only (no HTTP proxy)
    3. Let OpenRouter handle what it's good at: failover, provider selection,
       Exacto tool-calling quality, billing, prompt caching
    4. Keep local logic for what only YOU know: task complexity, subagent
       strategies, domain-specific routing, budget policy
    5. Zero additional latency - local router sets env vars, not network hops
"""

from __future__ import annotations

import os
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, TYPE_CHECKING

import yaml

# Optional SDK import - only needed if using build_options() with ClaudeAgentOptions
if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions

logger = logging.getLogger(__name__)

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ARGS_DIR = PROJECT_ROOT / "args"
ROUTING_CONFIG_PATH = ARGS_DIR / "routing.yaml"


# ---------------------------------------------------------------------------
# Model Definitions
# ---------------------------------------------------------------------------

class ModelTier(str, Enum):
    """Cost/capability tiers for model selection."""
    PREMIUM = "premium"
    STANDARD = "standard"
    EFFICIENT = "efficient"
    BUDGET = "budget"


@dataclass(frozen=True)
class ModelSpec:
    """
    A concrete model with its routing metadata.

    All model IDs use OpenRouter format (provider/model) since all traffic
    routes through OpenRouter regardless of the underlying provider.
    """
    id: str
    tier: ModelTier
    display_name: str
    supports_tool_calling: bool = True
    supports_extended_thinking: bool = False
    max_context_tokens: int = 200_000
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    use_exacto: bool = False

    @property
    def provider(self) -> str:
        return self.id.split("/")[0] if "/" in self.id else "anthropic"

    @property
    def routed_id(self) -> str:
        """Model ID with optional variant suffix for OpenRouter."""
        return f"{self.id}:exacto" if self.use_exacto else self.id


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

MODELS: dict[str, ModelSpec] = {
    # --- Premium ---
    "claude-sonnet-4.5": ModelSpec(
        id="anthropic/claude-sonnet-4-5",
        tier=ModelTier.PREMIUM,
        display_name="Claude Sonnet 4.5",
        supports_extended_thinking=True,
        cost_per_1m_input=3.0,
        cost_per_1m_output=15.0,
    ),
    "claude-sonnet-4.5-exacto": ModelSpec(
        id="anthropic/claude-sonnet-4-5",
        tier=ModelTier.PREMIUM,
        display_name="Claude Sonnet 4.5 (Exacto)",
        supports_extended_thinking=True,
        cost_per_1m_input=3.0,
        cost_per_1m_output=15.0,
        use_exacto=True,
    ),
    "claude-opus-4.5": ModelSpec(
        id="anthropic/claude-opus-4-5",
        tier=ModelTier.PREMIUM,
        display_name="Claude Opus 4.5",
        supports_extended_thinking=True,
        cost_per_1m_input=15.0,
        cost_per_1m_output=75.0,
    ),

    # --- Standard ---
    "gpt-4o": ModelSpec(
        id="openai/gpt-4o",
        tier=ModelTier.STANDARD,
        display_name="GPT-4o",
        max_context_tokens=128_000,
        cost_per_1m_input=2.50,
        cost_per_1m_output=10.0,
    ),
    "gemini-2.5-pro": ModelSpec(
        id="google/gemini-2.5-pro-preview",
        tier=ModelTier.STANDARD,
        display_name="Gemini 2.5 Pro",
        max_context_tokens=1_000_000,
        cost_per_1m_input=1.25,
        cost_per_1m_output=10.0,
    ),

    # --- Efficient ---
    "claude-haiku-4.5": ModelSpec(
        id="anthropic/claude-haiku-4-5",
        tier=ModelTier.EFFICIENT,
        display_name="Claude Haiku 4.5",
        cost_per_1m_input=0.80,
        cost_per_1m_output=4.0,
    ),
    "gpt-4o-mini": ModelSpec(
        id="openai/gpt-4o-mini",
        tier=ModelTier.EFFICIENT,
        display_name="GPT-4o Mini",
        max_context_tokens=128_000,
        cost_per_1m_input=0.15,
        cost_per_1m_output=0.60,
    ),

    # --- Budget ---
    "deepseek-v3": ModelSpec(
        id="deepseek/deepseek-chat-v3-0324",
        tier=ModelTier.BUDGET,
        display_name="DeepSeek V3",
        supports_tool_calling=True,
        max_context_tokens=128_000,
        cost_per_1m_input=0.28,
        cost_per_1m_output=0.42,
    ),

    # --- OpenRouter Auto Router ---
    "auto": ModelSpec(
        id="openrouter/auto",
        tier=ModelTier.STANDARD,
        display_name="OpenRouter Auto Router",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    ),
}


# ---------------------------------------------------------------------------
# Task Complexity Classification
# ---------------------------------------------------------------------------

class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComplexitySignals:
    """Heuristic signals - exposed for observability via Langfuse."""
    word_count: int = 0
    question_count: int = 0
    tool_keywords_found: list[str] = field(default_factory=list)
    reasoning_keywords_found: list[str] = field(default_factory=list)
    has_code_context: bool = False
    has_multi_step_indicators: bool = False
    explicit_complexity: TaskComplexity | None = None
    score: int = 0


# Default keyword sets (can be overridden via config)
_DEFAULT_TOOL_KEYWORDS = {
    "search", "fetch", "query", "database", "api", "call", "invoke",
    "create file", "edit", "update", "delete", "deploy", "execute",
}
_DEFAULT_REASONING_KEYWORDS = {
    "analyse", "analyze", "compare", "evaluate", "design", "architect",
    "plan", "strategy", "optimise", "optimize", "trade-off", "tradeoff",
    "pros and cons", "recommend", "debug", "investigate", "refactor",
}
_DEFAULT_MULTI_STEP_INDICATORS = {
    "then", "after that", "next", "finally", "step by step",
    "first", "second", "third", "also", "additionally",
}

# Default thresholds
_DEFAULT_THRESHOLDS = {
    "trivial_max": 1,
    "low_max": 3,
    "moderate_max": 6,
    "high_max": 10,
}


def classify_complexity(
    prompt: str,
    *,
    explicit: TaskComplexity | None = None,
    tool_count: int = 0,
    tool_keywords: set[str] | None = None,
    reasoning_keywords: set[str] | None = None,
    multi_step_indicators: set[str] | None = None,
    thresholds: dict[str, int] | None = None,
) -> tuple[TaskComplexity, ComplexitySignals]:
    """Heuristic complexity classifier. Zero latency, zero cost."""
    if explicit:
        return explicit, ComplexitySignals(explicit_complexity=explicit)

    # Use provided keywords or defaults
    tool_kw = tool_keywords or _DEFAULT_TOOL_KEYWORDS
    reason_kw = reasoning_keywords or _DEFAULT_REASONING_KEYWORDS
    multi_step = multi_step_indicators or _DEFAULT_MULTI_STEP_INDICATORS
    thresh = thresholds or _DEFAULT_THRESHOLDS

    prompt_lower = prompt.lower()
    words = prompt_lower.split()

    signals = ComplexitySignals(
        word_count=len(words),
        question_count=prompt.count("?"),
        tool_keywords_found=[k for k in tool_kw if k in prompt_lower],
        reasoning_keywords_found=[k for k in reason_kw if k in prompt_lower],
        has_code_context=any(m in prompt for m in ["```", "def ", "class ", "import "]),
        has_multi_step_indicators=any(i in prompt_lower for i in multi_step),
    )

    score = 0
    score += min(len(words) // 50, 3)
    score += len(signals.tool_keywords_found) * 2
    score += len(signals.reasoning_keywords_found) * 2
    score += 2 if signals.has_code_context else 0
    score += 2 if signals.has_multi_step_indicators else 0
    score += 1 if signals.question_count > 2 else 0
    score += 1 if tool_count > 5 else 0
    signals.score = score

    if score <= thresh.get("trivial_max", 1):
        return TaskComplexity.TRIVIAL, signals
    elif score <= thresh.get("low_max", 3):
        return TaskComplexity.LOW, signals
    elif score <= thresh.get("moderate_max", 6):
        return TaskComplexity.MODERATE, signals
    elif score <= thresh.get("high_max", 10):
        return TaskComplexity.HIGH, signals
    else:
        return TaskComplexity.CRITICAL, signals


# ---------------------------------------------------------------------------
# Subagent Alias Strategy
# ---------------------------------------------------------------------------

@dataclass
class SubagentStrategy:
    """Controls how 'sonnet'/'opus'/'haiku'/'inherit' aliases resolve."""
    sonnet_model: str
    opus_model: str
    haiku_model: str
    subagent_override: str | None = None

    def to_env(self) -> dict[str, str]:
        env = {
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self.sonnet_model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self.opus_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": self.haiku_model,
        }
        if self.subagent_override:
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = self.subagent_override
        return env


SUBAGENT_STRATEGIES: dict[TaskComplexity, SubagentStrategy] = {
    TaskComplexity.CRITICAL: SubagentStrategy(
        sonnet_model="anthropic/claude-sonnet-4-5",
        opus_model="anthropic/claude-opus-4-5",
        haiku_model="anthropic/claude-haiku-4-5",
    ),
    TaskComplexity.HIGH: SubagentStrategy(
        sonnet_model="anthropic/claude-sonnet-4-5",
        opus_model="anthropic/claude-sonnet-4-5",
        haiku_model="anthropic/claude-haiku-4-5",
    ),
    TaskComplexity.MODERATE: SubagentStrategy(
        sonnet_model="anthropic/claude-sonnet-4-5",
        opus_model="anthropic/claude-sonnet-4-5",
        haiku_model="anthropic/claude-haiku-4-5",
    ),
    TaskComplexity.LOW: SubagentStrategy(
        sonnet_model="anthropic/claude-haiku-4-5",
        opus_model="anthropic/claude-sonnet-4-5",
        haiku_model="anthropic/claude-haiku-4-5",
    ),
    TaskComplexity.TRIVIAL: SubagentStrategy(
        sonnet_model="anthropic/claude-haiku-4-5",
        opus_model="anthropic/claude-haiku-4-5",
        haiku_model="anthropic/claude-haiku-4-5",
    ),
}


# ---------------------------------------------------------------------------
# Routing Strategy
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecision:
    primary_model: ModelSpec
    subagent_strategy: SubagentStrategy
    complexity: TaskComplexity
    signals: ComplexitySignals
    reasoning: str


class RoutingProfile(str, Enum):
    QUALITY_FIRST = "quality_first"
    BALANCED = "balanced"
    COST_OPTIMISED = "cost_optimised"
    ANTHROPIC_ONLY = "anthropic_only"
    AUTO_ROUTER = "auto_router"


_ROUTING_TABLE: dict[RoutingProfile, dict[TaskComplexity, str]] = {
    RoutingProfile.QUALITY_FIRST: {
        TaskComplexity.CRITICAL: "claude-opus-4.5",
        TaskComplexity.HIGH:     "claude-sonnet-4.5-exacto",
        TaskComplexity.MODERATE: "claude-sonnet-4.5",
        TaskComplexity.LOW:      "claude-haiku-4.5",
        TaskComplexity.TRIVIAL:  "claude-haiku-4.5",
    },
    RoutingProfile.BALANCED: {
        TaskComplexity.CRITICAL: "claude-sonnet-4.5-exacto",
        TaskComplexity.HIGH:     "claude-sonnet-4.5",
        TaskComplexity.MODERATE: "gpt-4o",
        TaskComplexity.LOW:      "claude-haiku-4.5",
        TaskComplexity.TRIVIAL:  "gpt-4o-mini",
    },
    RoutingProfile.COST_OPTIMISED: {
        TaskComplexity.CRITICAL: "claude-sonnet-4.5-exacto",
        TaskComplexity.HIGH:     "gpt-4o",
        TaskComplexity.MODERATE: "gpt-4o-mini",
        TaskComplexity.LOW:      "gpt-4o-mini",
        TaskComplexity.TRIVIAL:  "deepseek-v3",
    },
    RoutingProfile.ANTHROPIC_ONLY: {
        TaskComplexity.CRITICAL: "claude-opus-4.5",
        TaskComplexity.HIGH:     "claude-sonnet-4.5-exacto",
        TaskComplexity.MODERATE: "claude-sonnet-4.5",
        TaskComplexity.LOW:      "claude-haiku-4.5",
        TaskComplexity.TRIVIAL:  "claude-haiku-4.5",
    },
    RoutingProfile.AUTO_ROUTER: {
        complexity: "auto" for complexity in TaskComplexity
    },
}


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@dataclass
class ObservabilityConfig:
    """
    Recommended stack:
        Layer 1: OpenRouter Dashboard (automatic, no config)
        Layer 2: Langfuse (OTEL traces - first-class Agent SDK integration)
        Layer 3: Helicone (optional gateway proxy - adds latency, use sparingly)
    """
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    helicone_enabled: bool = False
    helicone_api_key: str = ""

    local_stats: bool = True
    log_routing_decisions: bool = True
    log_to_dashboard: bool = True

    @classmethod
    def from_env(cls) -> "ObservabilityConfig":
        return cls(
            langfuse_enabled=bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
            langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            langfuse_base_url=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            helicone_enabled=bool(os.environ.get("HELICONE_API_KEY")),
            helicone_api_key=os.environ.get("HELICONE_API_KEY", ""),
        )

    @classmethod
    def from_config(cls, config: dict) -> "ObservabilityConfig":
        """Load observability config from routing.yaml."""
        obs_config = config.get("observability", {})
        langfuse = obs_config.get("langfuse", {})
        helicone = obs_config.get("helicone", {})

        # Load from env vars if specified in config
        langfuse_public_key = ""
        langfuse_secret_key = ""
        helicone_api_key = ""

        if langfuse.get("enabled"):
            key_env = langfuse.get("public_key_env", "LANGFUSE_PUBLIC_KEY")
            secret_env = langfuse.get("secret_key_env", "LANGFUSE_SECRET_KEY")
            langfuse_public_key = os.environ.get(key_env, "")
            langfuse_secret_key = os.environ.get(secret_env, "")

        if helicone.get("enabled"):
            key_env = helicone.get("api_key_env", "HELICONE_API_KEY")
            helicone_api_key = os.environ.get(key_env, "")

        return cls(
            langfuse_enabled=langfuse.get("enabled", False) and bool(langfuse_public_key),
            langfuse_public_key=langfuse_public_key,
            langfuse_secret_key=langfuse_secret_key,
            langfuse_base_url=langfuse.get("base_url", "https://cloud.langfuse.com"),
            helicone_enabled=helicone.get("enabled", False) and bool(helicone_api_key),
            helicone_api_key=helicone_api_key,
            local_stats=obs_config.get("local_stats", True),
            log_routing_decisions=obs_config.get("log_routing_decisions", True),
            log_to_dashboard=obs_config.get("log_to_dashboard", True),
        )


def setup_langfuse_tracing() -> None:
    """
    Configure Langfuse OTEL tracing for Claude Agent SDK.
    Call once at startup. Requires:
        pip install langfuse "langsmith[claude-agent-sdk]" "langsmith[otel]"
    """
    try:
        from langsmith.integrations.claude_agent_sdk import configure_claude_agent_sdk
        configure_claude_agent_sdk()
        logger.info("Langfuse OTEL tracing configured for Claude Agent SDK")
    except ImportError:
        logger.warning(
            "Langfuse/LangSmith not installed. "
            "pip install langfuse 'langsmith[claude-agent-sdk]' 'langsmith[otel]'"
        )


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------

class ModelRouter:
    """
    OpenRouter-first model router. NOT a proxy - zero network calls.

    1. Classifies task complexity (local heuristic)
    2. Looks up routing table (dict lookup)
    3. Builds env vars for ClaudeAgentOptions.env
    4. Returns options - Agent SDK calls OpenRouter directly
    """

    def __init__(
        self,
        profile: RoutingProfile = RoutingProfile.BALANCED,
        openrouter_api_key: str | None = None,
        observability: ObservabilityConfig | None = None,
        custom_routing_table: dict[TaskComplexity, str] | None = None,
        custom_subagent_strategies: dict[TaskComplexity, SubagentStrategy] | None = None,
        max_budget_usd: float | None = None,
        enabled: bool = True,
        fallback_to_direct: bool = True,
        tool_keywords: set[str] | None = None,
        reasoning_keywords: set[str] | None = None,
        multi_step_indicators: set[str] | None = None,
        thresholds: dict[str, int] | None = None,
        exacto_enabled: bool = True,
        exacto_min_complexity: TaskComplexity = TaskComplexity.HIGH,
        exacto_min_tool_count: int = 3,
    ):
        self.profile = profile
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.observability = observability or ObservabilityConfig.from_env()
        self.max_budget_usd = max_budget_usd
        self._routing_table = custom_routing_table or _ROUTING_TABLE[profile]
        self._subagent_strategies = custom_subagent_strategies or SUBAGENT_STRATEGIES
        self.enabled = enabled
        self.fallback_to_direct = fallback_to_direct

        # Complexity classification settings
        self.tool_keywords = tool_keywords or _DEFAULT_TOOL_KEYWORDS
        self.reasoning_keywords = reasoning_keywords or _DEFAULT_REASONING_KEYWORDS
        self.multi_step_indicators = multi_step_indicators or _DEFAULT_MULTI_STEP_INDICATORS
        self.thresholds = thresholds or _DEFAULT_THRESHOLDS

        # Exacto settings
        self.exacto_enabled = exacto_enabled
        self.exacto_min_complexity = exacto_min_complexity
        self.exacto_min_tool_count = exacto_min_tool_count

        if self.observability.langfuse_enabled:
            setup_langfuse_tracing()

        self._total_queries = 0
        self._query_log: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, config_path: Path | None = None) -> "ModelRouter":
        """
        Load router from args/routing.yaml.

        Args:
            config_path: Path to routing config (default: args/routing.yaml)

        Returns:
            Configured ModelRouter instance
        """
        config_path = config_path or ROUTING_CONFIG_PATH

        if not config_path.exists():
            logger.warning(f"Routing config not found at {config_path}, using defaults")
            return cls()

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load routing config: {e}, using defaults")
            return cls()

        routing_config = config.get("routing", {})
        budget_config = config.get("budget", {})
        complexity_config = config.get("complexity", {})
        exacto_config = config.get("exacto", {})

        # Parse profile
        profile_str = routing_config.get("profile", "anthropic_only")
        try:
            profile = RoutingProfile(profile_str)
        except ValueError:
            logger.warning(f"Invalid routing profile '{profile_str}', using anthropic_only")
            profile = RoutingProfile.ANTHROPIC_ONLY

        # Parse API key from env var
        api_key_env = routing_config.get("api_key_env", "OPENROUTER_API_KEY")
        openrouter_api_key = os.environ.get(api_key_env, "")

        # Parse observability
        observability = ObservabilityConfig.from_config(config)

        # Parse custom routing table if provided
        custom_routing_table = None
        if "routing_table" in config:
            custom_routing_table = {}
            for complexity_str, model_key in config["routing_table"].items():
                try:
                    complexity = TaskComplexity(complexity_str)
                    custom_routing_table[complexity] = model_key
                except ValueError:
                    logger.warning(f"Invalid complexity '{complexity_str}' in routing_table")

        # Parse custom subagent strategies if provided
        custom_subagent_strategies = None
        if "subagent_strategies" in config:
            custom_subagent_strategies = {}
            for complexity_str, strategy_config in config["subagent_strategies"].items():
                try:
                    complexity = TaskComplexity(complexity_str)
                    custom_subagent_strategies[complexity] = SubagentStrategy(
                        sonnet_model=strategy_config.get("sonnet_model", "anthropic/claude-sonnet-4-5"),
                        opus_model=strategy_config.get("opus_model", "anthropic/claude-opus-4-5"),
                        haiku_model=strategy_config.get("haiku_model", "anthropic/claude-haiku-4-5"),
                    )
                except ValueError:
                    logger.warning(f"Invalid complexity '{complexity_str}' in subagent_strategies")

        # Parse complexity keywords
        tool_keywords = set(complexity_config.get("tool_keywords", [])) or None
        reasoning_keywords = set(complexity_config.get("reasoning_keywords", [])) or None
        multi_step_indicators = set(complexity_config.get("multi_step_indicators", [])) or None
        thresholds = complexity_config.get("thresholds")

        # Parse exacto settings
        exacto_min_complexity_str = exacto_config.get("min_complexity", "high")
        try:
            exacto_min_complexity = TaskComplexity(exacto_min_complexity_str)
        except ValueError:
            exacto_min_complexity = TaskComplexity.HIGH

        return cls(
            profile=profile,
            openrouter_api_key=openrouter_api_key,
            observability=observability,
            custom_routing_table=custom_routing_table,
            custom_subagent_strategies=custom_subagent_strategies,
            max_budget_usd=budget_config.get("max_per_session_usd"),
            enabled=routing_config.get("enabled", True),
            fallback_to_direct=routing_config.get("fallback_to_direct", True),
            tool_keywords=tool_keywords,
            reasoning_keywords=reasoning_keywords,
            multi_step_indicators=multi_step_indicators,
            thresholds=thresholds,
            exacto_enabled=exacto_config.get("enabled", True),
            exacto_min_complexity=exacto_min_complexity,
            exacto_min_tool_count=exacto_config.get("min_tool_count", 3),
        )

    def route(
        self,
        prompt: str,
        *,
        explicit_complexity: TaskComplexity | None = None,
        explicit_model: str | None = None,
        tool_count: int = 0,
        requires_tool_calling: bool = True,
        use_exacto: bool | None = None,
    ) -> RoutingDecision:
        """Determine model for a prompt. Pure function, no side effects."""

        if explicit_model and explicit_model in MODELS:
            model = MODELS[explicit_model]
            complexity = explicit_complexity or TaskComplexity.MODERATE
            return RoutingDecision(
                primary_model=model,
                subagent_strategy=self._subagent_strategies.get(
                    complexity, SUBAGENT_STRATEGIES[TaskComplexity.MODERATE]
                ),
                complexity=complexity,
                signals=ComplexitySignals(explicit_complexity=complexity),
                reasoning=f"Explicit model override: {model.display_name}",
            )

        if self.profile == RoutingProfile.AUTO_ROUTER:
            complexity = explicit_complexity or TaskComplexity.MODERATE
            return RoutingDecision(
                primary_model=MODELS["auto"],
                subagent_strategy=self._subagent_strategies.get(
                    complexity, SUBAGENT_STRATEGIES[TaskComplexity.MODERATE]
                ),
                complexity=complexity,
                signals=ComplexitySignals(explicit_complexity=complexity),
                reasoning="Auto Router: delegated to OpenRouter.",
            )

        complexity, signals = classify_complexity(
            prompt,
            explicit=explicit_complexity,
            tool_count=tool_count,
            tool_keywords=self.tool_keywords,
            reasoning_keywords=self.reasoning_keywords,
            multi_step_indicators=self.multi_step_indicators,
            thresholds=self.thresholds,
        )

        model_key = self._routing_table.get(complexity, "claude-sonnet-4.5")
        if model_key not in MODELS:
            logger.warning(f"Model '{model_key}' not in registry, falling back")
            model_key = "claude-sonnet-4.5"
        model = MODELS[model_key]

        # Apply Exacto if conditions are met
        should_use_exacto = use_exacto
        if should_use_exacto is None and self.exacto_enabled:
            complexity_order = [TaskComplexity.TRIVIAL, TaskComplexity.LOW,
                               TaskComplexity.MODERATE, TaskComplexity.HIGH, TaskComplexity.CRITICAL]
            complexity_index = complexity_order.index(complexity)
            min_index = complexity_order.index(self.exacto_min_complexity)
            should_use_exacto = (
                complexity_index >= min_index and
                tool_count >= self.exacto_min_tool_count
            )

        if should_use_exacto is not None and should_use_exacto != model.use_exacto:
            variant = f"{model_key}-exacto" if should_use_exacto else model_key.replace("-exacto", "")
            if variant in MODELS:
                model = MODELS[variant]

        if requires_tool_calling and not model.supports_tool_calling:
            model = MODELS["claude-haiku-4.5"]
            logger.warning(f"Tool calling required, fell back to {model.display_name}")

        subagent_strategy = self._subagent_strategies.get(
            complexity, SUBAGENT_STRATEGIES[TaskComplexity.MODERATE]
        )

        return RoutingDecision(
            primary_model=model,
            subagent_strategy=subagent_strategy,
            complexity=complexity,
            signals=signals,
            reasoning=(
                f"Complexity={complexity.value} (score={signals.score}). "
                f"Profile={self.profile.value} -> {model.display_name}"
                f"{' [Exacto]' if model.use_exacto else ''}. "
                f"Subagents: sonnet->{subagent_strategy.sonnet_model.split('/')[-1]}, "
                f"haiku->{subagent_strategy.haiku_model.split('/')[-1]}."
            ),
        )

    def build_options_dict(
        self,
        decision: RoutingDecision,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Build options dict for DexAIClient. Sets env vars only - no network calls.

        Returns dict with:
            - model: The model ID to use
            - env: Environment variables to set
            - complexity: The classified complexity
            - reasoning: Human-readable explanation
            - exacto: Whether Exacto is enabled
        """
        env: dict[str, str] = {}

        # Transport: OpenRouter (or Helicone -> OpenRouter if enabled)
        if self.observability.helicone_enabled:
            env["ANTHROPIC_BASE_URL"] = "https://openrouter.helicone.ai/api"
            env["HELICONE_AUTH"] = f"Bearer {self.observability.helicone_api_key}"
        else:
            env["ANTHROPIC_BASE_URL"] = "https://openrouter.ai/api"

        env["ANTHROPIC_AUTH_TOKEN"] = self.openrouter_api_key
        env["ANTHROPIC_API_KEY"] = ""

        # Subagent aliases
        env.update(decision.subagent_strategy.to_env())

        # Prompt caching only works for Anthropic models via Anthropic Skin
        if decision.primary_model.provider != "anthropic":
            env["DISABLE_PROMPT_CACHING"] = "1"

        if extra_env:
            env.update(extra_env)

        # Local tracking
        self._total_queries += 1
        query_entry = {
            "timestamp": time.time(),
            "complexity": decision.complexity.value,
            "model": decision.primary_model.routed_id,
            "exacto": decision.primary_model.use_exacto,
            "reasoning": decision.reasoning,
        }
        self._query_log.append(query_entry)

        if self.observability.log_routing_decisions:
            logger.info(f"Query #{self._total_queries}: {decision.reasoning}")

        # Log to dashboard if enabled
        if self.observability.log_to_dashboard:
            self._log_to_dashboard(decision)

        return {
            "model": decision.primary_model.routed_id,
            "env": env,
            "complexity": decision.complexity.value,
            "reasoning": decision.reasoning,
            "exacto": decision.primary_model.use_exacto,
            "max_budget_usd": self.max_budget_usd,
        }

    def build_options(
        self,
        decision: RoutingDecision,
        *,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict | None = None,
        permission_mode: str | None = None,
        max_turns: int | None = None,
        extra_env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> "ClaudeAgentOptions":
        """
        Build ClaudeAgentOptions. Sets env vars only - no network calls.

        Requires claude_agent_sdk to be installed.
        """
        try:
            from claude_agent_sdk import ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "claude_agent_sdk required for build_options(). "
                "Use build_options_dict() for dict-based options."
            )

        options_dict = self.build_options_dict(decision, extra_env=extra_env)

        return ClaudeAgentOptions(
            model=options_dict["model"],
            system_prompt=system_prompt,
            allowed_tools=allowed_tools or [],
            mcp_servers=mcp_servers or {},
            permission_mode=permission_mode,
            max_turns=max_turns,
            env=options_dict["env"],
            max_budget_usd=self.max_budget_usd,
            **kwargs,
        )

    def _log_to_dashboard(self, decision: RoutingDecision) -> None:
        """Log routing decision to dashboard database."""
        try:
            from tools.dashboard.backend.database import record_routing_decision
            record_routing_decision(
                user_id="system",  # Will be overridden by caller if needed
                complexity=decision.complexity.value,
                model=decision.primary_model.routed_id,
                exacto=decision.primary_model.use_exacto,
                reasoning=decision.reasoning,
            )
        except ImportError:
            pass  # Dashboard module not available
        except Exception as e:
            logger.debug(f"Failed to log routing decision to dashboard: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Lightweight local stats. Use Langfuse/OpenRouter for production."""
        model_counts: dict[str, int] = {}
        complexity_counts: dict[str, int] = {}
        exacto_count = 0
        for entry in self._query_log:
            model_counts[entry["model"]] = model_counts.get(entry["model"], 0) + 1
            complexity_counts[entry["complexity"]] = complexity_counts.get(entry["complexity"], 0) + 1
            if entry.get("exacto"):
                exacto_count += 1
        return {
            "total_queries": self._total_queries,
            "model_distribution": model_counts,
            "complexity_distribution": complexity_counts,
            "exacto_queries": exacto_count,
            "profile": self.profile.value,
        }


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

async def routed_query(
    prompt: str,
    router: ModelRouter,
    *,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    mcp_servers: dict | None = None,
    explicit_complexity: TaskComplexity | None = None,
    explicit_model: str | None = None,
    use_exacto: bool | None = None,
    **kwargs: Any,
) -> AsyncIterator:
    """Classify -> route -> build options -> query in one call."""
    try:
        from claude_agent_sdk import query
    except ImportError:
        raise ImportError("claude_agent_sdk required for routed_query()")

    decision = router.route(
        prompt,
        explicit_complexity=explicit_complexity,
        explicit_model=explicit_model,
        tool_count=len(allowed_tools or []),
        use_exacto=use_exacto,
    )
    options = router.build_options(
        decision,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        mcp_servers=mcp_servers,
        **kwargs,
    )
    async for message in query(prompt=prompt, options=options):
        yield message
