"""
Memory Extraction Pipeline

Provides the heuristic gate, extraction queue, and session note extractor
for the DexAI memory system. See goals/memory_context_compaction_design.md.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "args" / "memory.yaml"
