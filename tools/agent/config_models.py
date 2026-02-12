from __future__ import annotations

import logging
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, ConfigDict

from tools.agent import ARGS_DIR

logger = logging.getLogger(__name__)


# =============================================================================
# AgentConfig (args/agent.yaml)
# =============================================================================

class AgentSettingsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="claude-sonnet-4-20250514")
    use_routing: bool = Field(default=True)
    routing_config: str = Field(default="args/routing.yaml")
    working_directory: Optional[str] = None
    max_tokens: int = Field(default=4096, ge=1)
    permission_mode: str = Field(default="default")
    session_timeout_minutes: int = Field(default=60, ge=1)


class ToolsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    allowed_builtin: list[str] = Field(default_factory=list)
    require_confirmation: list[str] = Field(default_factory=list)
    dexai_tools: list[str] = Field(default_factory=list)


class SystemPromptConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    base: str = Field(default="")
    include_memory: bool = Field(default=True)
    include_commitments: bool = Field(default=True)
    include_energy: bool = Field(default=True)


class ADHDResponseConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_length_chat: int = Field(default=500, ge=1)
    max_length_detailed: int = Field(default=2000, ge=1)
    strip_preamble: bool = Field(default=True)
    one_thing_mode: bool = Field(default=True)


class ADHDTasksConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    auto_decompose: bool = Field(default=True)
    show_friction: bool = Field(default=True)
    energy_aware: bool = Field(default=True)
    max_steps_shown: int = Field(default=1, ge=1)


class ADHDLanguageConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    filter_enabled: bool = Field(default=True)
    filter_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class ADHDContextConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    auto_capture: bool = Field(default=True)
    staleness_days: int = Field(default=7, ge=1)
    max_stored: int = Field(default=50, ge=1)


class ADHDConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    response: ADHDResponseConfig = Field(default_factory=ADHDResponseConfig)
    tasks: ADHDTasksConfig = Field(default_factory=ADHDTasksConfig)
    language: ADHDLanguageConfig = Field(default_factory=ADHDLanguageConfig)
    context: ADHDContextConfig = Field(default_factory=ADHDContextConfig)


class SandboxNetworkConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    allow_local_binding: bool = Field(default=True)
    allow_unix_sockets: list[str] = Field(default_factory=list)


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    auto_allow_bash_if_sandboxed: bool = Field(default=True)
    excluded_commands: list[str] = Field(default_factory=list)
    allow_unsandboxed_commands: bool = Field(default=False)
    network: SandboxNetworkConfig = Field(default_factory=SandboxNetworkConfig)


class SubagentsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    default_model: str = Field(default="haiku")
    allowed_tools: list[str] = Field(default_factory=list)


class CostsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    track_enabled: bool = Field(default=True)
    daily_limit_usd: float = Field(default=10.0, ge=0)
    warning_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    limit_action: str = Field(default="notify_and_degrade")


class SkillsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    allow_self_modification: bool = Field(default=True)
    writable_directory: str = Field(default=".claude/skills")
    protected_skills: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    agent: AgentSettingsConfig = Field(default_factory=AgentSettingsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    system_prompt: SystemPromptConfig = Field(default_factory=SystemPromptConfig)
    adhd: ADHDConfig = Field(default_factory=ADHDConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    subagents: SubagentsConfig = Field(default_factory=SubagentsConfig)
    costs: CostsConfig = Field(default_factory=CostsConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)


# =============================================================================
# RoutingConfig (args/routing.yaml)
# =============================================================================

class RoutingSettingsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    profile: str = Field(default="anthropic_only")
    enabled: bool = Field(default=True)
    api_key_env: str = Field(default="OPENROUTER_API_KEY")
    fallback_to_direct: bool = Field(default=True)


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_per_session_usd: Optional[float] = Field(default=5.0, ge=0)
    max_per_day_usd: Optional[float] = Field(default=50.0, ge=0)
    max_per_user_per_day_usd: Optional[float] = Field(default=10.0, ge=0)
    limit_action: str = Field(default="notify_and_degrade")


class ComplexityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    tool_keywords: list[str] = Field(default_factory=list)
    reasoning_keywords: list[str] = Field(default_factory=list)
    multi_step_indicators: list[str] = Field(default_factory=list)
    thresholds: dict[str, int] = Field(default_factory=dict)


class ExactoConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    min_complexity: str = Field(default="high")
    min_tool_count: int = Field(default=3, ge=0)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    routing: RoutingSettingsConfig = Field(default_factory=RoutingSettingsConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    complexity: ComplexityConfig = Field(default_factory=ComplexityConfig)
    exacto: ExactoConfig = Field(default_factory=ExactoConfig)


# =============================================================================
# MemoryConfig (args/memory.yaml)
# =============================================================================

class EmbeddingsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="text-embedding-3-small")
    dimensions: int = Field(default=1536, ge=1)
    batch_size: int = Field(default=100, ge=1)
    requests_per_minute: int = Field(default=500, ge=1)
    cache_enabled: bool = Field(default=True)


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    default_type: str = Field(default="hybrid")
    default_limit: int = Field(default=10, ge=1)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    hybrid: dict[str, float] = Field(default_factory=lambda: {"keyword_weight": 0.3, "semantic_weight": 0.7})
    recency_boost: bool = Field(default=True)
    recency_decay_days: int = Field(default=30, ge=1)


class ExtractionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    gate_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    extraction_model: str = Field(default="claude-haiku-4-5-20251001")
    batch_size: int = Field(default=5, ge=1)
    flush_interval_seconds: float = Field(default=5.0, ge=0.1)
    max_queue_size: int = Field(default=1000, ge=1)


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: dict[str, Any] = Field(default_factory=lambda: {"active": "native"})
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)


# =============================================================================
# MultimodalConfig (args/multimodal.yaml)
# =============================================================================

class VisionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    provider: str = Field(default="anthropic")
    max_images_per_message: int = Field(default=3, ge=1)
    max_cost_per_image: float = Field(default=0.05, ge=0)


class DocumentsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    extract_text: bool = Field(default=True)
    max_pages: int = Field(default=20, ge=1)
    max_chars_per_doc: int = Field(default=10000, ge=1)
    supported_formats: list[str] = Field(default_factory=lambda: ["pdf", "docx", "txt", "md"])


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    max_file_size_mb: int = Field(default=50, ge=1)
    max_processing_cost_usd: float = Field(default=0.20, ge=0)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    documents: DocumentsConfig = Field(default_factory=DocumentsConfig)


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    model: str = Field(default="dall-e-3")
    max_cost_per_image: float = Field(default=0.10, ge=0)
    default_size: str = Field(default="1024x1024")
    default_quality: str = Field(default="standard")


class MultimodalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


# =============================================================================
# SecurityConfig (args/security.yaml)
# =============================================================================

class SessionSecurityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    token_bytes: int = Field(default=32, ge=16)
    default_ttl_hours: int = Field(default=24, ge=1)
    max_ttl_hours: int = Field(default=168, ge=1)
    extend_on_activity: bool = Field(default=True)
    max_concurrent: int = Field(default=5, ge=1)
    channel_binding: bool = Field(default=True)
    idle_timeout_hours: int = Field(default=4, ge=1)


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_failed_attempts: int = Field(default=5, ge=1)
    lockout_duration_minutes: int = Field(default=15, ge=1)
    sensitive_ops_reauth: bool = Field(default=True)
    allowed_methods: list[str] = Field(default_factory=lambda: ["token", "api_key"])


class AuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    level: str = Field(default="standard")
    retention_days: int = Field(default=90, ge=1)
    events: list[str] = Field(default_factory=list)
    include_request_body: bool = Field(default=False)
    mask_fields: list[str] = Field(default_factory=list)


class InputValidationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_message_bytes: int = Field(default=10240, ge=1)
    strip_html: bool = Field(default=True)
    unicode_normalization: str = Field(default="NFC")
    injection_detection: bool = Field(default=True)
    pattern_blocking: bool = Field(default=True)
    log_blocked: bool = Field(default=True)


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    session: SessionSecurityConfig = Field(default_factory=SessionSecurityConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    input: InputValidationConfig = Field(default_factory=InputValidationConfig)


# =============================================================================
# WorkspaceConfig (args/workspace.yaml)
# =============================================================================

class WorkspaceScopeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: str = Field(default="persistent")
    cleanup: dict[str, Any] = Field(default_factory=lambda: {"stale_days": 30, "cleanup_on_startup": True})


class WorkspaceTemplatesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str = Field(default="docs/templates")
    bootstrap_files: list[str] = Field(default_factory=list)


class WorkspaceAccessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    default: str = Field(default="rw")


class WorkspaceRestrictionsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_file_size_bytes: int = Field(default=10485760, ge=1)
    max_workspace_size_bytes: int = Field(default=104857600, ge=1)
    blocked_extensions: list[str] = Field(default_factory=list)


class WorkspaceSettingsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = Field(default=True)
    base_path: str = Field(default="data/workspaces")
    scope: WorkspaceScopeConfig = Field(default_factory=WorkspaceScopeConfig)
    templates: WorkspaceTemplatesConfig = Field(default_factory=WorkspaceTemplatesConfig)
    access: WorkspaceAccessConfig = Field(default_factory=WorkspaceAccessConfig)
    restrictions: WorkspaceRestrictionsConfig = Field(default_factory=WorkspaceRestrictionsConfig)


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    workspace: WorkspaceSettingsConfig = Field(default_factory=WorkspaceSettingsConfig)


# =============================================================================
# load_and_validate
# =============================================================================

_CONFIG_MAP: dict[str, type[BaseModel]] = {
    "agent": AgentConfig,
    "routing": RoutingConfig,
    "memory": MemoryConfig,
    "multimodal": MultimodalConfig,
    "security": SecurityConfig,
    "workspace": WorkspaceConfig,
}


def load_and_validate(config_name: str, model_class: type[BaseModel] | None = None) -> BaseModel:
    if model_class is None:
        model_class = _CONFIG_MAP.get(config_name)
        if model_class is None:
            raise ValueError(f"Unknown config: {config_name}. Available: {list(_CONFIG_MAP.keys())}")

    yaml_path = ARGS_DIR / f"{config_name}.yaml"

    try:
        if yaml_path.exists():
            with open(yaml_path) as f:
                raw = yaml.safe_load(f) or {}
        else:
            raw = {}

        return model_class.model_validate(raw)
    except Exception as e:
        logger.warning(f"Config validation failed for {config_name}: {e}, using defaults")
        return model_class()
