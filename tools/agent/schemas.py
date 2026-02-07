"""
JSON Schemas for structured SDK output.

These schemas enable the Claude Agent SDK to return validated JSON responses
for specific ADHD use cases like task decomposition, energy assessment, and
commitment tracking.

Usage:
    from tools.agent.schemas import TASK_DECOMPOSITION_SCHEMA

    options = ClaudeAgentOptions(
        output_format=TASK_DECOMPOSITION_SCHEMA,
        ...
    )

    async for message in query(prompt="What's next?", options=options):
        if message.type == "result":
            structured = message.structured_output  # Guaranteed to match schema
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Task Decomposition Schema
# =============================================================================

TASK_DECOMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "current_step": {
                "type": "object",
                "description": "The ONE next physical action to take",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Single concrete physical action (not abstract goal)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Estimated time in minutes (ideally 5-15)",
                        "minimum": 1,
                        "maximum": 60,
                    },
                    "energy_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Energy required to complete this step",
                    },
                    "done_when": {
                        "type": "string",
                        "description": "What 'done' looks like - concrete completion criteria",
                    },
                },
                "required": ["action", "duration_minutes", "energy_level"],
            },
            "remaining_steps": {
                "type": "integer",
                "description": "Approximate count of remaining steps (after current)",
                "minimum": 0,
            },
            "blockers": {
                "type": "array",
                "description": "Potential friction points that might stall progress",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": [
                                "missing_info",
                                "unclear_requirements",
                                "environment",
                                "decision_paralysis",
                                "emotional",
                            ],
                        },
                        "solution": {
                            "type": "string",
                            "description": "How to resolve this blocker",
                        },
                    },
                    "required": ["description", "category"],
                },
            },
            "acknowledgment": {
                "type": "string",
                "description": "RSD-safe acknowledgment of the task/feeling (optional)",
            },
        },
        "required": ["current_step", "remaining_steps"],
    },
}


# =============================================================================
# Energy Assessment Schema
# =============================================================================

ENERGY_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "detected_energy": {
                "type": "string",
                "enum": ["low", "medium", "high", "unknown"],
                "description": "Detected or reported energy level",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in energy detection (0.0-1.0)",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "cues_detected": {
                "type": "array",
                "description": "Signals used to detect energy level",
                "items": {"type": "string"},
            },
            "suggested_task": {
                "type": "object",
                "description": "Task matched to current energy",
                "properties": {
                    "description": {"type": "string"},
                    "energy_required": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "duration_minutes": {"type": "integer"},
                    "why_good_fit": {
                        "type": "string",
                        "description": "Why this task matches current energy",
                    },
                },
                "required": ["description", "energy_required"],
            },
            "alternative_task": {
                "type": "object",
                "description": "Alternative if user wants to push themselves",
                "properties": {
                    "description": {"type": "string"},
                    "energy_required": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "warning": {
                        "type": "string",
                        "description": "RSD-safe note about energy mismatch",
                    },
                },
            },
            "ask_energy": {
                "type": "boolean",
                "description": "Should we ask the user to clarify their energy level?",
            },
        },
        "required": ["detected_energy", "confidence"],
    },
}


# =============================================================================
# Commitment List Schema
# =============================================================================

COMMITMENT_LIST_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "commitments": {
                "type": "array",
                "description": "Active commitments (RSD-safe, no 'overdue' language)",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Commitment identifier",
                        },
                        "content": {
                            "type": "string",
                            "description": "What was committed to",
                        },
                        "to_person": {
                            "type": "string",
                            "description": "Who the commitment was made to",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["open", "in_progress", "completed"],
                            "description": "Current status (never 'overdue')",
                        },
                        "created_at": {
                            "type": "string",
                            "description": "When commitment was made (friendly format)",
                        },
                        "estimated_duration": {
                            "type": "string",
                            "description": "How long it might take",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Urgency level (without shame)",
                        },
                    },
                    "required": ["content", "status"],
                },
            },
            "summary": {
                "type": "object",
                "description": "Summary of commitments",
                "properties": {
                    "total": {"type": "integer"},
                    "open": {"type": "integer"},
                    "in_progress": {"type": "integer"},
                    "completed_today": {"type": "integer"},
                },
            },
            "suggested_next": {
                "type": "string",
                "description": "Which commitment to tackle first (RSD-safe suggestion)",
            },
        },
        "required": ["commitments"],
    },
}


# =============================================================================
# Friction Check Schema
# =============================================================================

FRICTION_CHECK_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "friction_found": {
                "type": "boolean",
                "description": "Whether any friction points were identified",
            },
            "blockers": {
                "type": "array",
                "description": "Identified friction points",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "What the blocker is",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "missing_info",
                                "unclear_requirements",
                                "environment",
                                "decision_paralysis",
                                "emotional",
                            ],
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "How much this will stall progress",
                        },
                        "solution": {
                            "type": "string",
                            "description": "Suggested resolution",
                        },
                        "can_solve_now": {
                            "type": "boolean",
                            "description": "Can this be solved immediately?",
                        },
                    },
                    "required": ["description", "category", "severity"],
                },
            },
            "ready_to_proceed": {
                "type": "boolean",
                "description": "Whether task can proceed (no blockers or all solvable)",
            },
            "message": {
                "type": "string",
                "description": "RSD-safe summary message",
            },
        },
        "required": ["friction_found", "ready_to_proceed"],
    },
}


# =============================================================================
# Current Step Schema (One-Thing Mode)
# =============================================================================

CURRENT_STEP_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "step": {
                "type": "object",
                "description": "The ONE thing to do right now",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Single physical action in imperative form",
                    },
                    "context": {
                        "type": "string",
                        "description": "Brief context (what this is part of)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 30,
                    },
                },
                "required": ["action"],
            },
            "friction": {
                "type": "string",
                "description": "Any friction to solve first (or null if clear)",
            },
            "after_this": {
                "type": "string",
                "description": "Brief hint about what comes next (keeps momentum)",
            },
        },
        "required": ["step"],
    },
}


# =============================================================================
# Schema Registry
# =============================================================================

SCHEMAS: dict[str, dict[str, Any]] = {
    "task_decomposition": TASK_DECOMPOSITION_SCHEMA,
    "energy_assessment": ENERGY_ASSESSMENT_SCHEMA,
    "commitment_list": COMMITMENT_LIST_SCHEMA,
    "friction_check": FRICTION_CHECK_SCHEMA,
    "current_step": CURRENT_STEP_SCHEMA,
}


def get_schema(name: str) -> dict[str, Any] | None:
    """
    Get a schema by name.

    Args:
        name: Schema name (e.g., "task_decomposition")

    Returns:
        Schema dict or None if not found
    """
    return SCHEMAS.get(name)


def list_schemas() -> list[str]:
    """
    List all available schema names.

    Returns:
        List of schema names
    """
    return list(SCHEMAS.keys())


# =============================================================================
# Helper Functions
# =============================================================================


def validate_output_format(output_format: dict[str, Any]) -> bool:
    """
    Validate that an output format dict has the required structure.

    Args:
        output_format: Output format dict to validate

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(output_format, dict):
        return False
    if output_format.get("type") != "json_schema":
        return False
    if "schema" not in output_format:
        return False
    schema = output_format["schema"]
    if not isinstance(schema, dict):
        return False
    if schema.get("type") != "object":
        return False
    return True


def create_custom_schema(
    properties: dict[str, Any],
    required: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Create a custom output format schema.

    Args:
        properties: Schema properties dict
        required: List of required property names
        description: Optional schema description

    Returns:
        Output format dict suitable for ClaudeAgentOptions

    Example:
        schema = create_custom_schema(
            properties={
                "task": {"type": "string"},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5}
            },
            required=["task"]
        )
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    if description:
        schema["description"] = description

    return {
        "type": "json_schema",
        "schema": schema,
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for viewing schemas."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DexAI Structured Output Schemas")
    parser.add_argument("--list", action="store_true", help="List all schemas")
    parser.add_argument("--show", help="Show specific schema")
    parser.add_argument(
        "--format", choices=["json", "compact"], default="json", help="Output format"
    )

    args = parser.parse_args()

    if args.list:
        print("Available Schemas:")
        print("-" * 40)
        for name in list_schemas():
            schema = get_schema(name)
            if schema:
                props = schema["schema"].get("properties", {})
                print(f"  {name}: {len(props)} properties")

    elif args.show:
        schema = get_schema(args.show)
        if schema:
            if args.format == "json":
                print(json.dumps(schema, indent=2))
            else:
                print(json.dumps(schema))
        else:
            print(f"Schema not found: {args.show}")
            print(f"Available: {', '.join(list_schemas())}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
