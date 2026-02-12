"""
DexAI Skill MCP Tools

Exposes skill validation, testing, and listing as MCP tools
for the Claude Agent SDK.

Tools:
- dexai_validate_skill: Validate a skill for correctness
- dexai_test_skill: Test a skill by parsing and simulating execution
- dexai_list_skills: List all available skills with validation status

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent invokes them as needed during conversations.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Tool: dexai_validate_skill
# =============================================================================


def dexai_validate_skill(skill_name: str) -> dict[str, Any]:
    """Validate a skill for correctness. Returns validation errors and warnings.

    Checks file existence, YAML frontmatter, required fields, dangerous
    patterns, file size limits, and internal references.

    Args:
        skill_name: Name of the skill (e.g., 'adhd-decomposition') or path
            to a skill directory.

    Returns:
        Dict with success status, validation result, and any errors/warnings.
    """
    try:
        from tools.agent.skill_validator import validate_skill

        result = validate_skill(skill_name)

        return {
            "success": True,
            "tool": "dexai_validate_skill",
            "skill_name": skill_name,
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_validate_skill",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_test_skill
# =============================================================================


def dexai_test_skill(
    skill_name: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Test a skill by parsing and simulating execution.

    Runs validation plus structural checks: frontmatter parsing,
    content structure, and internal reference integrity.

    Args:
        skill_name: Name of the skill (e.g., 'adhd-decomposition') or path.
        dry_run: If True, only validates without executing. Default True.

    Returns:
        Dict with success status, test results, and pass/fail counts.
    """
    try:
        from tools.agent.skill_validator import test_skill

        result = test_skill(skill_name, dry_run=dry_run)

        return {
            "success": result.get("success", False),
            "tool": "dexai_test_skill",
            "skill_name": skill_name,
            "dry_run": dry_run,
            "tests_passed": result.get("tests_passed", 0),
            "tests_total": result.get("tests_total", 0),
            "test_results": result.get("test_results", []),
            "validation": result.get("validation", {}),
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_test_skill",
            "error": str(e),
        }


# =============================================================================
# Tool: dexai_list_skills
# =============================================================================


def dexai_list_skills() -> dict[str, Any]:
    """List all available skills with validation status.

    Scans the default skills directory and returns metadata for each skill
    including name, path, validation status, and description.

    Returns:
        Dict with success status and list of skill summaries.
    """
    try:
        from tools.agent.skill_validator import list_skills

        skills = list_skills()

        return {
            "success": True,
            "tool": "dexai_list_skills",
            "count": len(skills),
            "skills": skills,
        }

    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_list_skills",
            "error": str(e),
        }


# =============================================================================
# Tool Registry
# =============================================================================


SKILL_TOOLS = {
    "dexai_validate_skill": {
        "function": dexai_validate_skill,
        "description": "Validate a skill for correctness, checking frontmatter, safety, and structure",
        "parameters": {
            "skill_name": {"type": "string", "required": True},
        },
    },
    "dexai_test_skill": {
        "function": dexai_test_skill,
        "description": "Test a skill by parsing and simulating execution",
        "parameters": {
            "skill_name": {"type": "string", "required": True},
            "dry_run": {"type": "boolean", "required": False, "default": True},
        },
    },
    "dexai_list_skills": {
        "function": dexai_list_skills,
        "description": "List all available skills with validation status",
        "parameters": {},
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = SKILL_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available skill tools."""
    return list(SKILL_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing skill tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI Skill MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available skill tools:")
        for name, info in SKILL_TOOLS.items():
            print(f"  {name}: {info['description']}")
        return

    tool_func = get_tool(args.tool)
    if not tool_func:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {list_tools()}")
        sys.exit(1)

    # Parse arguments
    tool_args = {}
    if args.args:
        tool_args = json.loads(args.args)

    # Invoke tool
    result = tool_func(**tool_args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
