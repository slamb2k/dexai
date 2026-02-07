"""
Memory Provider Package

This package provides a pluggable memory provider architecture for DexAI,
allowing swapping between different memory backends (native SQLite, Mem0, Zep,
OpenMemory, etc.) while preserving ADHD-safe design principles and the
existing MCP tool interface.

Architecture:
    MCP Tools (unchanged) → MemoryService (facade) → MemoryProvider (abstract)
                                                          ↓
                                              ┌───────────┼───────────┐
                                              ↓           ↓           ↓
                                          Native     Mem0Adapter  ZepAdapter
                                         (SQLite)

Usage:
    from tools.memory.providers import get_provider, MemoryService
    from tools.memory.providers.base import MemoryType, MemoryEntry

    # Get configured provider
    service = MemoryService()
    await service.initialize()

    # Add memory
    entry_id = await service.add("User prefers dark mode", type=MemoryType.PREFERENCE)

    # Search
    results = await service.search("user preferences")
"""

from .base import (
    BootstrapResult,
    Commitment,
    ContextSnapshot,
    DependencyStatus,
    DeploymentMode,
    DeployResult,
    HealthStatus,
    MemoryEntry,
    MemoryProvider,
    MemorySource,
    MemoryType,
    SearchFilters,
)
from .native import NativeProvider


__all__ = [
    "BootstrapResult",
    "Commitment",
    "ContextSnapshot",
    "DependencyStatus",
    "DeployResult",
    "DeploymentMode",
    "HealthStatus",
    # Data structures
    "MemoryEntry",
    # Base class
    "MemoryProvider",
    "MemorySource",
    "MemoryType",
    # Providers
    "NativeProvider",
    "SearchFilters",
]


def get_provider(name: str, config: dict | None = None) -> MemoryProvider:
    """
    Get a provider instance by name.

    Args:
        name: Provider name (native, mem0, zep, simplemem, claudemem)
        config: Provider configuration

    Returns:
        MemoryProvider instance

    Raises:
        ValueError: If provider not found
        ImportError: If provider dependencies not installed
    """
    config = config or {}

    if name == "native":
        return NativeProvider(config)

    elif name == "mem0":
        try:
            from .mem0_provider import Mem0Provider

            return Mem0Provider(config)
        except ImportError as e:
            raise ImportError(
                "Mem0 provider requires mem0ai package. Install with: pip install dexai[mem0]"
            ) from e

    elif name == "zep":
        try:
            from .zep_provider import ZepProvider

            return ZepProvider(config)
        except ImportError as e:
            raise ImportError(
                "Zep provider requires zep-python package. Install with: pip install dexai[zep]"
            ) from e

    elif name == "simplemem":
        try:
            from .simplemem_provider import SimpleMemProvider

            return SimpleMemProvider(config)
        except ImportError as e:
            raise ImportError(
                "SimpleMem provider requires httpx package (should be installed by default)"
            ) from e

    elif name == "claudemem":
        try:
            from .claudemem_provider import ClaudeMemProvider

            return ClaudeMemProvider(config)
        except ImportError as e:
            raise ImportError(
                "ClaudeMem provider requires httpx package (should be installed by default)"
            ) from e

    else:
        raise ValueError(
            f"Unknown provider: {name}. "
            f"Available providers: native, mem0, zep, simplemem, claudemem"
        )
