"""Policy Validator — Validate policy definitions before saving

This module ensures policy definitions are valid and safe before they are
saved to the database. It checks required fields, validates condition
operators against allowed fields, and ensures action types are valid.

Philosophy:
    Invalid policies should be caught early, before they can cause
    unexpected behavior. Clear error messages help users understand
    and fix issues with their policy definitions.

Usage:
    # Validate a policy definition
    from tools.office.policies.validator import validate_policy_definition
    result = validate_policy_definition(policy_data)
    if not result["valid"]:
        for error in result["errors"]:
            print(f"Error: {error}")

    # Validate a single condition
    from tools.office.policies.validator import validate_condition
    valid, error = validate_condition(condition, "inbox")

    # Validate a single action
    from tools.office.policies.validator import validate_action
    valid, error = validate_action(action, "calendar")
"""

import re
import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office.policies import (
    ActionType,
    ConditionOperator,
    PolicyType,
)


# Valid fields for each policy type
VALID_FIELDS: dict[str, set[str]] = {
    "inbox": {
        "from_address",
        "from_domain",
        "from_name",
        "to_count",
        "cc_count",
        "subject",
        "body",
        "has_attachments",
        "is_reply",
        "is_forward",
        "labels",
        "age_hours",
        "is_read",
        "thread_message_count",
        "is_starred",
        "snippet",
    },
    "calendar": {
        "organizer",
        "organizer_domain",
        "attendee_count",
        "duration_minutes",
        "is_recurring",
        "time_of_day",
        "day_of_week",
        "conflicts_with",
        "title",
        "location",
        "is_all_day",
    },
    "response": {
        "is_first_contact_today",
        "from_domain",
        "from_address",
        "subject",
        "is_reply",
    },
    "schedule": {
        "time_of_day",
        "day_of_week",
        "is_weekend",
    },
    "any": {
        "current_flow_state",
    },
}


# Valid actions for each policy type
VALID_ACTIONS_BY_TYPE: dict[str, set[str]] = {
    "inbox": {
        "archive",
        "delete",
        "label",
        "mark_read",
        "star",
        "forward",
        "auto_reply",
        "notify_immediately",
        "notify_digest",
        "suppress",
        "ignore_flow_state",
        "escalate",
    },
    "calendar": {
        "accept",
        "decline",
        "tentative",
        "suggest_alternative",
        "notify_immediately",
        "notify_digest",
        "suppress",
        "escalate",
    },
    "response": {
        "auto_reply",
        "escalate",
    },
    "schedule": {
        "notify_immediately",
        "notify_digest",
        "suppress",
    },
}


# Actions that require specific parameters
REQUIRED_PARAMETERS: dict[str, list[str]] = {
    "label": ["label"],
    "forward": ["to"],
    "auto_reply": ["template"],
    "suggest_alternative": [],  # Optional: days_ahead, prefer_morning, etc.
}


# Operators valid for specific field types
NUMERIC_OPERATORS = {"greater_than", "less_than", "equals"}
STRING_OPERATORS = {"equals", "contains", "starts_with", "ends_with", "matches_regex"}
LIST_OPERATORS = {"in_list", "not_in_list", "contains"}
BOOLEAN_OPERATORS = {"equals"}
VIP_OPERATORS = {"in_vip_list"}
EMPTY_OPERATORS = {"is_empty"}


# Field type classifications
NUMERIC_FIELDS = {
    "to_count",
    "cc_count",
    "age_hours",
    "thread_message_count",
    "attendee_count",
    "duration_minutes",
    "time_of_day",
    "day_of_week",
}
BOOLEAN_FIELDS = {
    "has_attachments",
    "is_reply",
    "is_forward",
    "is_read",
    "is_starred",
    "is_recurring",
    "is_all_day",
    "is_weekend",
    "is_first_contact_today",
}
LIST_FIELDS = {"labels", "conflicts_with"}
ADDRESS_FIELDS = {"from_address", "organizer"}


def validate_policy_definition(policy_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a complete policy definition.

    Performs comprehensive validation:
    1. Check required fields are present
    2. Validate policy_type is valid
    3. Validate each condition has valid field and operator
    4. Validate each action has valid action_type
    5. Check parameters are valid for action type
    6. Check for logical inconsistencies

    Args:
        policy_data: Policy definition dictionary

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str]
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check required fields
    required_fields = ["name", "policy_type", "conditions", "actions"]
    for field in required_fields:
        if field not in policy_data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Validate policy_type
    policy_type = policy_data["policy_type"]
    if not PolicyType.values() or policy_type not in PolicyType.values():
        errors.append(
            f"Invalid policy_type: {policy_type}. "
            f"Valid types: {PolicyType.values()}"
        )
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Validate conditions
    conditions = policy_data.get("conditions", [])
    if not isinstance(conditions, list):
        errors.append("conditions must be a list")
    elif len(conditions) == 0:
        warnings.append("Policy has no conditions - it will match everything")
    else:
        for i, condition in enumerate(conditions):
            valid, error = validate_condition(condition, policy_type)
            if not valid:
                errors.append(f"Condition {i + 1}: {error}")

    # Validate actions
    actions = policy_data.get("actions", [])
    if not isinstance(actions, list):
        errors.append("actions must be a list")
    elif len(actions) == 0:
        errors.append("Policy must have at least one action")
    else:
        for i, action in enumerate(actions):
            valid, error = validate_action(action, policy_type)
            if not valid:
                errors.append(f"Action {i + 1}: {error}")

    # Validate optional fields
    if "priority" in policy_data:
        priority = policy_data["priority"]
        if not isinstance(priority, int) or priority < 0:
            errors.append("priority must be a non-negative integer")

    if "enabled" in policy_data:
        if not isinstance(policy_data["enabled"], bool):
            errors.append("enabled must be a boolean")

    if "max_executions_per_day" in policy_data:
        max_exec = policy_data["max_executions_per_day"]
        if max_exec is not None and (not isinstance(max_exec, int) or max_exec <= 0):
            errors.append("max_executions_per_day must be a positive integer or null")

    if "cooldown_minutes" in policy_data:
        cooldown = policy_data["cooldown_minutes"]
        if cooldown is not None and (not isinstance(cooldown, int) or cooldown < 0):
            errors.append("cooldown_minutes must be a non-negative integer or null")

    # Check for logical issues
    logical_warnings = check_logical_issues(policy_data)
    warnings.extend(logical_warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_condition(
    condition: dict[str, Any],
    policy_type: str,
) -> tuple[bool, str]:
    """
    Validate a single condition.

    Checks that:
    - Required fields (field, operator, value) are present
    - Field is valid for the policy type
    - Operator is valid for the field type
    - Value type matches the operator expectations

    Args:
        condition: Condition dictionary
        policy_type: The policy type (for field validation)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    if not isinstance(condition, dict):
        return False, "Condition must be a dictionary"

    if "field" not in condition:
        return False, "Missing 'field'"
    if "operator" not in condition:
        return False, "Missing 'operator'"
    if "value" not in condition:
        return False, "Missing 'value'"

    field = condition["field"]
    operator = condition["operator"]
    value = condition["value"]

    # Validate field
    valid_fields = VALID_FIELDS.get(policy_type, set()) | VALID_FIELDS.get("any", set())
    if field not in valid_fields:
        # Check if it's a nested field (e.g., sender.address)
        base_field = field.split(".")[0]
        if base_field not in valid_fields:
            return (
                False,
                f"Invalid field '{field}' for policy type '{policy_type}'. "
                f"Valid fields: {sorted(valid_fields)}",
            )

    # Validate operator
    if not ConditionOperator.values() or operator not in ConditionOperator.values():
        return (
            False,
            f"Invalid operator '{operator}'. "
            f"Valid operators: {sorted(ConditionOperator.values())}",
        )

    # Validate operator is appropriate for field type
    field_type_error = validate_operator_for_field(field, operator)
    if field_type_error:
        return False, field_type_error

    # Validate value type
    value_error = validate_value_for_operator(operator, value)
    if value_error:
        return False, value_error

    return True, ""


def validate_action(
    action: dict[str, Any],
    policy_type: str,
) -> tuple[bool, str]:
    """
    Validate a single action.

    Checks that:
    - action_type is present and valid
    - action_type is valid for the policy type
    - Required parameters are present

    Args:
        action: Action dictionary
        policy_type: The policy type (for action validation)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(action, dict):
        return False, "Action must be a dictionary"

    if "action_type" not in action:
        return False, "Missing 'action_type'"

    action_type = action["action_type"]

    # Validate action_type exists
    if not ActionType.values() or action_type not in ActionType.values():
        return (
            False,
            f"Invalid action_type '{action_type}'. "
            f"Valid types: {sorted(ActionType.values())}",
        )

    # Validate action_type is valid for policy type
    valid_actions = VALID_ACTIONS_BY_TYPE.get(policy_type, set())
    if action_type not in valid_actions:
        return (
            False,
            f"Action '{action_type}' not valid for policy type '{policy_type}'. "
            f"Valid actions: {sorted(valid_actions)}",
        )

    # Check required parameters
    required_params = REQUIRED_PARAMETERS.get(action_type, [])
    parameters = action.get("parameters", {})

    for param in required_params:
        if param not in parameters:
            return (
                False,
                f"Action '{action_type}' requires parameter '{param}'",
            )

    return True, ""


def validate_operator_for_field(field: str, operator: str) -> str | None:
    """
    Validate that an operator is appropriate for a field type.

    Args:
        field: The field name
        operator: The operator

    Returns:
        Error message if invalid, None if valid
    """
    # VIP list operator only for address fields
    if operator == "in_vip_list":
        if field not in ADDRESS_FIELDS and not field.endswith("_address"):
            return f"Operator 'in_vip_list' only valid for address fields, not '{field}'"

    # Numeric operators for numeric fields
    if operator in {"greater_than", "less_than"}:
        if field not in NUMERIC_FIELDS:
            return f"Operator '{operator}' only valid for numeric fields, not '{field}'"

    # is_empty can be used on any field
    # in_list/not_in_list can be used on string fields

    return None


def validate_value_for_operator(operator: str, value: Any) -> str | None:
    """
    Validate that a value is appropriate for an operator.

    Args:
        operator: The operator
        value: The value

    Returns:
        Error message if invalid, None if valid
    """
    if operator in {"in_list", "not_in_list"}:
        if not isinstance(value, list):
            return f"Operator '{operator}' requires a list value"

    if operator in {"greater_than", "less_than"}:
        if not isinstance(value, (int, float)):
            return f"Operator '{operator}' requires a numeric value"

    if operator == "matches_regex":
        if not isinstance(value, str):
            return "Operator 'matches_regex' requires a string pattern"
        try:
            re.compile(value)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

    if operator == "is_empty":
        # Value is ignored for is_empty, any value is fine
        pass

    if operator in {"equals"} and isinstance(value, (dict, list)):
        return f"Operator 'equals' should not use complex value types"

    return None


def check_logical_issues(policy_data: dict[str, Any]) -> list[str]:
    """
    Check for logical issues in a policy definition.

    Looks for patterns that may indicate user errors or suboptimal policies.

    Args:
        policy_data: Policy definition dictionary

    Returns:
        List of warning messages
    """
    warnings: list[str] = []
    conditions = policy_data.get("conditions", [])
    actions = policy_data.get("actions", [])

    # Check for conflicting conditions
    seen_fields: dict[str, list[tuple[str, Any]]] = {}
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        field = condition.get("field", "")
        operator = condition.get("operator", "")
        value = condition.get("value")

        if field not in seen_fields:
            seen_fields[field] = []
        seen_fields[field].append((operator, value))

    for field, ops in seen_fields.items():
        if len(ops) > 1:
            # Check for equals with different values
            equals_values = [v for op, v in ops if op == "equals"]
            if len(equals_values) > 1:
                warnings.append(
                    f"Field '{field}' has multiple 'equals' conditions - "
                    "only one can match at a time"
                )

    # Check for destructive actions without safeguards
    destructive_actions = {"delete", "forward"}
    has_destructive = any(
        a.get("action_type") in destructive_actions
        for a in actions
        if isinstance(a, dict)
    )
    if has_destructive and len(conditions) < 2:
        warnings.append(
            "Policy has destructive actions with few conditions - "
            "consider adding more conditions for safety"
        )

    # Check for high priority without VIP check
    priority = policy_data.get("priority", 0)
    has_vip_check = any(
        c.get("operator") == "in_vip_list"
        for c in conditions
        if isinstance(c, dict)
    )
    if priority >= 90 and not has_vip_check:
        warnings.append(
            "High priority policy without VIP check may override VIP handling"
        )

    return warnings


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Policy Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a policy from JSON file
  python validator.py --file policy.json

  # Validate a policy from JSON string
  python validator.py --data '{"name": "Test", ...}'

  # List valid fields for a policy type
  python validator.py --list-fields inbox

  # List valid actions for a policy type
  python validator.py --list-actions calendar
        """,
    )

    parser.add_argument("--file", metavar="PATH", help="Path to policy JSON file")
    parser.add_argument("--data", metavar="JSON", help="Policy JSON string")
    parser.add_argument("--list-fields", metavar="TYPE", help="List valid fields for policy type")
    parser.add_argument("--list-actions", metavar="TYPE", help="List valid actions for policy type")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list_fields:
        policy_type = args.list_fields
        fields = VALID_FIELDS.get(policy_type, set()) | VALID_FIELDS.get("any", set())
        if args.json:
            print(json.dumps({"policy_type": policy_type, "fields": sorted(fields)}, indent=2))
        else:
            print(f"Valid fields for '{policy_type}':")
            for field in sorted(fields):
                field_type = "numeric" if field in NUMERIC_FIELDS else (
                    "boolean" if field in BOOLEAN_FIELDS else (
                        "list" if field in LIST_FIELDS else "string"
                    )
                )
                print(f"  - {field} ({field_type})")
        sys.exit(0)

    if args.list_actions:
        policy_type = args.list_actions
        actions = VALID_ACTIONS_BY_TYPE.get(policy_type, set())
        if args.json:
            print(json.dumps({"policy_type": policy_type, "actions": sorted(actions)}, indent=2))
        else:
            print(f"Valid actions for '{policy_type}':")
            for action in sorted(actions):
                required = REQUIRED_PARAMETERS.get(action, [])
                params_str = f" (requires: {', '.join(required)})" if required else ""
                print(f"  - {action}{params_str}")
        sys.exit(0)

    if args.file or args.data:
        if args.file:
            with open(args.file) as f:
                policy_data = json.load(f)
        else:
            policy_data = json.loads(args.data)

        result = validate_policy_definition(policy_data)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["valid"]:
                print("OK: Policy definition is valid")
            else:
                print("INVALID: Policy definition has errors")
                for error in result["errors"]:
                    print(f"  ERROR: {error}")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  WARN: {warning}")

        sys.exit(0 if result["valid"] else 1)

    # Default: run self-tests
    print("Testing policy validator...")

    # Test valid policy
    valid_policy = {
        "name": "Test Policy",
        "policy_type": "inbox",
        "conditions": [
            {"field": "from_domain", "operator": "equals", "value": "example.com"},
            {"field": "age_hours", "operator": "greater_than", "value": 24},
        ],
        "actions": [
            {"action_type": "archive"},
            {"action_type": "mark_read"},
        ],
        "priority": 10,
        "enabled": True,
    }
    result = validate_policy_definition(valid_policy)
    assert result["valid"], f"Expected valid policy, got errors: {result['errors']}"

    # Test missing required field
    missing_name = {
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(missing_name)
    assert not result["valid"]
    assert any("name" in e for e in result["errors"])

    # Test invalid policy_type
    bad_type = {
        "name": "Test",
        "policy_type": "invalid_type",
        "conditions": [{"field": "from_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_type)
    assert not result["valid"]
    assert any("policy_type" in e for e in result["errors"])

    # Test invalid field for policy type
    bad_field = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "organizer_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_field)
    assert not result["valid"]
    assert any("organizer_domain" in e for e in result["errors"])

    # Test invalid operator
    bad_operator = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "invalid_op", "value": "x.com"}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_operator)
    assert not result["valid"]
    assert any("operator" in e for e in result["errors"])

    # Test invalid action for policy type
    bad_action = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "accept"}],  # Calendar action, not inbox
    }
    result = validate_policy_definition(bad_action)
    assert not result["valid"]
    assert any("accept" in e for e in result["errors"])

    # Test missing required parameter
    missing_param = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "label"}],  # Missing 'label' parameter
    }
    result = validate_policy_definition(missing_param)
    assert not result["valid"]
    assert any("label" in e for e in result["errors"])

    # Test invalid regex
    bad_regex = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "subject", "operator": "matches_regex", "value": "[invalid"}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_regex)
    assert not result["valid"]
    assert any("regex" in e.lower() for e in result["errors"])

    # Test numeric operator on string field
    bad_numeric = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "greater_than", "value": 10}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_numeric)
    assert not result["valid"]
    assert any("numeric" in e.lower() for e in result["errors"])

    # Test VIP operator on non-address field
    bad_vip = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "subject", "operator": "in_vip_list", "value": True}],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(bad_vip)
    assert not result["valid"]
    assert any("vip" in e.lower() for e in result["errors"])

    # Test validate_condition directly
    valid, error = validate_condition(
        {"field": "from_domain", "operator": "equals", "value": "test.com"},
        "inbox",
    )
    assert valid, f"Expected valid condition, got: {error}"

    valid, error = validate_condition(
        {"field": "invalid_field", "operator": "equals", "value": "test"},
        "inbox",
    )
    assert not valid
    assert "invalid_field" in error.lower()

    # Test validate_action directly
    valid, error = validate_action({"action_type": "archive"}, "inbox")
    assert valid, f"Expected valid action, got: {error}"

    valid, error = validate_action({"action_type": "accept"}, "inbox")
    assert not valid
    assert "accept" in error.lower()

    # Test warning for no conditions
    no_conditions = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [],
        "actions": [{"action_type": "archive"}],
    }
    result = validate_policy_definition(no_conditions)
    assert result["valid"]  # Valid but with warning
    assert len(result["warnings"]) > 0
    assert any("no conditions" in w.lower() for w in result["warnings"])

    # Test warning for destructive action with few conditions
    destructive_few = {
        "name": "Test",
        "policy_type": "inbox",
        "conditions": [{"field": "from_domain", "operator": "equals", "value": "x.com"}],
        "actions": [{"action_type": "delete"}],
    }
    result = validate_policy_definition(destructive_few)
    assert result["valid"]
    assert any("destructive" in w.lower() for w in result["warnings"])

    print("OK: All policy validator tests passed")
    sys.exit(0)
