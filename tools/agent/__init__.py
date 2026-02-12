"""
DexAI Agent Module

Provides Claude Agent SDK integration for DexAI with ADHD-aware features.

Components:
- sdk_client.py: Main ClaudeSDKClient wrapper with DexAI defaults
- permissions.py: SDK can_use_tool callback mapping DexAI RBAC
- mcp/: Custom MCP tools exposing DexAI's unique ADHD features

Usage:
    from tools.agent import DexAIClient, create_permission_callback
    from tools.agent.constants import OWNER_USER_ID

    # Create client with DexAI defaults
    client = DexAIClient()

    # Query the agent
    response = await client.query("What's my next task?")
"""

from pathlib import Path

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
TOOLS_ROOT = Path(__file__).parent.parent
AGENT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
ARGS_DIR = PROJECT_ROOT / "args"
CONFIG_PATH = ARGS_DIR / "agent.yaml"

# Database paths
DB_PATH = DATA_DIR / "agent.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Single-tenant constant
from tools.agent.constants import OWNER_USER_ID

# Exports
__all__ = [
    "PROJECT_ROOT",
    "TOOLS_ROOT",
    "AGENT_ROOT",
    "DATA_DIR",
    "ARGS_DIR",
    "CONFIG_PATH",
    "DB_PATH",
    "OWNER_USER_ID",
    # System prompt exports (lazy loaded)
    "SystemPromptBuilder",
    "PromptContext",
    "PromptMode",
    "SessionType",
    "SESSION_FILE_ALLOWLISTS",
    "bootstrap_workspace",
    "is_workspace_bootstrapped",
    # Schema exports (lazy loaded)
    "TASK_DECOMPOSITION_SCHEMA",
    "ENERGY_ASSESSMENT_SCHEMA",
    "COMMITMENT_LIST_SCHEMA",
    "FRICTION_CHECK_SCHEMA",
    "CURRENT_STEP_SCHEMA",
    "get_schema",
    "list_schemas",
    "create_custom_schema",
    # Model selector exports (lazy loaded)
    "ModelSelector",
    "get_model_for_agent",
    "score_task_complexity",
    # Skill tracker exports (lazy loaded)
    "SkillTracker",
    "SkillUsageData",
    # Skill validator exports (lazy loaded)
    "SkillValidationResult",
    "validate_skill",
    "test_skill",
    "list_skills",
    "compute_skill_hash",
    # Workspace manager exports (lazy loaded)
    "WorkspaceManager",
    "WorkspaceScope",
    "WorkspaceAccess",
    "get_workspace_manager",
]


def __getattr__(name):
    """Lazy load components to avoid circular imports."""
    # System prompt components
    system_prompt_exports = (
        "SystemPromptBuilder",
        "PromptContext",
        "PromptMode",
        "SessionType",
        "SESSION_FILE_ALLOWLISTS",
        "bootstrap_workspace",
        "is_workspace_bootstrapped",
    )
    if name in system_prompt_exports:
        from tools.agent.system_prompt import (
            SystemPromptBuilder,
            PromptContext,
            PromptMode,
            SessionType,
            SESSION_FILE_ALLOWLISTS,
            bootstrap_workspace,
            is_workspace_bootstrapped,
        )
        return {
            "SystemPromptBuilder": SystemPromptBuilder,
            "PromptContext": PromptContext,
            "PromptMode": PromptMode,
            "SessionType": SessionType,
            "SESSION_FILE_ALLOWLISTS": SESSION_FILE_ALLOWLISTS,
            "bootstrap_workspace": bootstrap_workspace,
            "is_workspace_bootstrapped": is_workspace_bootstrapped,
        }[name]

    # Schema components
    schema_exports = (
        "TASK_DECOMPOSITION_SCHEMA",
        "ENERGY_ASSESSMENT_SCHEMA",
        "COMMITMENT_LIST_SCHEMA",
        "FRICTION_CHECK_SCHEMA",
        "CURRENT_STEP_SCHEMA",
        "get_schema",
        "list_schemas",
        "create_custom_schema",
    )
    if name in schema_exports:
        from tools.agent.schemas import (
            TASK_DECOMPOSITION_SCHEMA,
            ENERGY_ASSESSMENT_SCHEMA,
            COMMITMENT_LIST_SCHEMA,
            FRICTION_CHECK_SCHEMA,
            CURRENT_STEP_SCHEMA,
            get_schema,
            list_schemas,
            create_custom_schema,
        )
        return {
            "TASK_DECOMPOSITION_SCHEMA": TASK_DECOMPOSITION_SCHEMA,
            "ENERGY_ASSESSMENT_SCHEMA": ENERGY_ASSESSMENT_SCHEMA,
            "COMMITMENT_LIST_SCHEMA": COMMITMENT_LIST_SCHEMA,
            "FRICTION_CHECK_SCHEMA": FRICTION_CHECK_SCHEMA,
            "CURRENT_STEP_SCHEMA": CURRENT_STEP_SCHEMA,
            "get_schema": get_schema,
            "list_schemas": list_schemas,
            "create_custom_schema": create_custom_schema,
        }[name]

    # Model selector components
    model_selector_exports = (
        "ModelSelector",
        "get_model_for_agent",
        "score_task_complexity",
    )
    if name in model_selector_exports:
        from tools.agent.model_selector import (
            ModelSelector,
            get_model_for_agent,
            score_task_complexity,
        )
        return {
            "ModelSelector": ModelSelector,
            "get_model_for_agent": get_model_for_agent,
            "score_task_complexity": score_task_complexity,
        }[name]

    # Skill tracker components
    skill_tracker_exports = (
        "SkillTracker",
        "SkillUsageData",
    )
    if name in skill_tracker_exports:
        from tools.agent.skill_tracker import (
            SkillTracker,
            SkillUsageData,
        )
        return {
            "SkillTracker": SkillTracker,
            "SkillUsageData": SkillUsageData,
        }[name]

    # Skill validator components
    skill_validator_exports = (
        "SkillValidationResult",
        "validate_skill",
        "test_skill",
        "list_skills",
        "compute_skill_hash",
    )
    if name in skill_validator_exports:
        from tools.agent.skill_validator import (
            SkillValidationResult,
            validate_skill,
            test_skill,
            list_skills,
            compute_skill_hash,
        )
        return {
            "SkillValidationResult": SkillValidationResult,
            "validate_skill": validate_skill,
            "test_skill": test_skill,
            "list_skills": list_skills,
            "compute_skill_hash": compute_skill_hash,
        }[name]

    # Workspace manager components
    workspace_exports = (
        "WorkspaceManager",
        "WorkspaceScope",
        "WorkspaceAccess",
        "get_workspace_manager",
    )
    if name in workspace_exports:
        from tools.agent.workspace_manager import (
            WorkspaceManager,
            WorkspaceScope,
            WorkspaceAccess,
            get_workspace_manager,
        )
        return {
            "WorkspaceManager": WorkspaceManager,
            "WorkspaceScope": WorkspaceScope,
            "WorkspaceAccess": WorkspaceAccess,
            "get_workspace_manager": get_workspace_manager,
        }[name]

    # Client factory components
    client_factory_exports = (
        "load_config",
        "build_system_prompt",
        "DEFAULT_CONFIG",
        "SKILLS_AUTHORIZATION",
    )
    if name in client_factory_exports:
        from tools.agent.client_factory import (
            load_config,
            build_system_prompt,
            DEFAULT_CONFIG,
            SKILLS_AUTHORIZATION,
        )
        return {
            "load_config": load_config,
            "build_system_prompt": build_system_prompt,
            "DEFAULT_CONFIG": DEFAULT_CONFIG,
            "SKILLS_AUTHORIZATION": SKILLS_AUTHORIZATION,
        }[name]

    # Query engine components
    query_engine_exports = (
        "DexAIClient",
        "_extract_session_id",
    )
    if name in query_engine_exports:
        from tools.agent.query_engine import (
            DexAIClient,
            _extract_session_id,
        )
        return {
            "DexAIClient": DexAIClient,
            "_extract_session_id": _extract_session_id,
        }[name]

    # Response formatter components
    response_formatter_exports = (
        "QueryResult",
        "StructuredQueryResult",
        "strip_preamble",
        "quick_query",
        "quick_decompose",
        "quick_energy_match",
        "quick_friction_check",
        "quick_current_step",
    )
    if name in response_formatter_exports:
        from tools.agent.response_formatter import (
            QueryResult,
            StructuredQueryResult,
            strip_preamble,
            quick_query,
            quick_decompose,
            quick_energy_match,
            quick_friction_check,
            quick_current_step,
        )
        return {
            "QueryResult": QueryResult,
            "StructuredQueryResult": StructuredQueryResult,
            "strip_preamble": strip_preamble,
            "quick_query": quick_query,
            "quick_decompose": quick_decompose,
            "quick_energy_match": quick_energy_match,
            "quick_friction_check": quick_friction_check,
            "quick_current_step": quick_current_step,
        }[name]

    # Fall through for submodule imports (e.g., "sdk_client")
    import importlib
    try:
        return importlib.import_module(f".{name}", __name__)
    except ImportError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
