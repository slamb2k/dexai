"""
DexAI SDK Client — Public API facade.

This module re-exports all public symbols from the split submodules
to preserve existing import paths throughout the codebase.
"""
from tools.agent import ARGS_DIR, PROJECT_ROOT
from tools.agent.client_factory import (
    load_config,
    build_system_prompt,
    DEFAULT_CONFIG,
    SKILLS_AUTHORIZATION,
)

CONFIG_DIR = ARGS_DIR  # alias for backward compatibility
from tools.agent.query_engine import DexAIClient
from tools.agent.response_formatter import (
    QueryResult,
    StructuredQueryResult,
    quick_query,
    quick_decompose,
    quick_energy_match,
    quick_friction_check,
    quick_current_step,
)

from tools.agent.query_engine import _extract_session_id

__all__ = [
    "DexAIClient",
    "QueryResult",
    "StructuredQueryResult",
    "load_config",
    "build_system_prompt",
    "ARGS_DIR",
    "PROJECT_ROOT",
    "CONFIG_DIR",
    "DEFAULT_CONFIG",
    "SKILLS_AUTHORIZATION",
    "_extract_session_id",
    "quick_query",
    "quick_decompose",
    "quick_energy_match",
    "quick_friction_check",
    "quick_current_step",
]


def main():
    from tools.agent.query_engine import main as _main
    _main()


if __name__ == "__main__":
    main()
