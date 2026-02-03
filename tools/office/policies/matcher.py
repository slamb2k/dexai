"""Policy Condition Matcher — Match conditions against event data

This module provides the condition matching engine for policy evaluation.
Given a set of conditions and event data, it determines whether all
conditions are satisfied.

Supported Fields:
    Email events:
        - from_address: Full sender email address
        - from_domain: Domain part of sender email
        - from_name: Display name of sender
        - to_count: Number of recipients in To field
        - cc_count: Number of recipients in CC field
        - subject: Email subject line
        - body: Email body text
        - has_attachments: Boolean, whether email has attachments
        - is_reply: Boolean, whether email is a reply (Re:)
        - is_forward: Boolean, whether email is a forward (Fwd:)
        - labels: List of label/folder names
        - age_hours: Hours since email was received

    Calendar events:
        - organizer: Organizer email address
        - organizer_domain: Domain of organizer
        - attendee_count: Number of attendees
        - duration_minutes: Event duration in minutes
        - is_recurring: Boolean, whether event recurs
        - time_of_day: Hour of day (0-23) when event starts
        - day_of_week: Day of week (0=Monday, 6=Sunday)
        - conflicts_with: List of conflicting event IDs

    Universal:
        - current_flow_state: Current focus/flow state (focused, available, dnd)

Field Paths:
    Nested fields can be accessed with dot notation:
        - "sender.domain" extracts domain from sender object
        - "organizer.name" extracts name from organizer object
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office.policies import (
    ConditionOperator,
    PolicyCondition,
    VIPContact,
    get_connection,
)


def extract_field_value(field: str, event_data: dict[str, Any]) -> Any:
    """
    Extract a field value from event data, supporting nested paths.

    Supports dot notation for nested access (e.g., "sender.domain").
    Returns None if the path doesn't exist.

    Args:
        field: Field name or dot-separated path
        event_data: Event data dictionary

    Returns:
        The field value, or None if not found
    """
    if "." not in field:
        return event_data.get(field)

    parts = field.split(".")
    current = event_data

    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    return current


def get_vip_emails(account_id: str) -> set[str]:
    """
    Get the set of VIP email addresses for an account.

    Args:
        account_id: The account to get VIP contacts for

    Returns:
        Set of lowercase email addresses
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT email FROM office_vip_contacts WHERE account_id = ?",
        (account_id,),
    )

    vip_emails = {row["email"].lower() for row in cursor.fetchall()}
    conn.close()

    return vip_emails


def match_condition(
    condition: PolicyCondition,
    event_data: dict[str, Any],
    vip_emails: set[str] | None = None,
) -> bool:
    """
    Check if a single condition matches the event data.

    Args:
        condition: The condition to evaluate
        event_data: Event data dictionary
        vip_emails: Set of VIP email addresses (for IN_VIP_LIST operator)

    Returns:
        True if the condition matches, False otherwise
    """
    field_value = extract_field_value(condition.field, event_data)
    expected_value = condition.value
    operator = condition.operator

    # Handle None field values
    if field_value is None:
        if operator == ConditionOperator.IS_EMPTY:
            return True
        return False

    # Normalize strings for comparison
    if isinstance(field_value, str):
        field_value_lower = field_value.lower()
    else:
        field_value_lower = field_value

    if isinstance(expected_value, str):
        expected_value_lower = expected_value.lower()
    else:
        expected_value_lower = expected_value

    if operator == ConditionOperator.EQUALS:
        if isinstance(field_value, str) and isinstance(expected_value, str):
            return field_value_lower == expected_value_lower
        return field_value == expected_value

    if operator == ConditionOperator.CONTAINS:
        if isinstance(field_value, str):
            return expected_value_lower in field_value_lower
        if isinstance(field_value, list):
            if isinstance(expected_value, str):
                return any(
                    expected_value_lower == (item.lower() if isinstance(item, str) else item)
                    for item in field_value
                )
            return expected_value in field_value
        return False

    if operator == ConditionOperator.STARTS_WITH:
        if isinstance(field_value, str):
            return field_value_lower.startswith(expected_value_lower)
        return False

    if operator == ConditionOperator.ENDS_WITH:
        if isinstance(field_value, str):
            return field_value_lower.endswith(expected_value_lower)
        return False

    if operator == ConditionOperator.MATCHES_REGEX:
        if isinstance(field_value, str):
            try:
                return bool(re.search(expected_value, field_value, re.IGNORECASE))
            except re.error:
                return False
        return False

    if operator == ConditionOperator.GREATER_THAN:
        try:
            return float(field_value) > float(expected_value)
        except (ValueError, TypeError):
            return False

    if operator == ConditionOperator.LESS_THAN:
        try:
            return float(field_value) < float(expected_value)
        except (ValueError, TypeError):
            return False

    if operator == ConditionOperator.IN_LIST:
        if not isinstance(expected_value, list):
            return False
        if isinstance(field_value, str):
            expected_lower = [
                v.lower() if isinstance(v, str) else v for v in expected_value
            ]
            return field_value_lower in expected_lower
        return field_value in expected_value

    if operator == ConditionOperator.NOT_IN_LIST:
        if not isinstance(expected_value, list):
            return True
        if isinstance(field_value, str):
            expected_lower = [
                v.lower() if isinstance(v, str) else v for v in expected_value
            ]
            return field_value_lower not in expected_lower
        return field_value not in expected_value

    if operator == ConditionOperator.IS_EMPTY:
        if isinstance(field_value, str):
            return len(field_value.strip()) == 0
        if isinstance(field_value, list):
            return len(field_value) == 0
        return field_value is None

    if operator == ConditionOperator.IN_VIP_LIST:
        if vip_emails is None:
            return False
        if isinstance(field_value, str):
            return field_value_lower in vip_emails
        return False

    return False


def match_all_conditions(
    conditions: list[PolicyCondition],
    event_data: dict[str, Any],
    account_id: str | None = None,
) -> bool:
    """
    Check if all conditions match the event data.

    All conditions must match for the policy to trigger (AND logic).
    If any condition uses IN_VIP_LIST, the VIP list is loaded once.

    Args:
        conditions: List of conditions to evaluate
        event_data: Event data dictionary
        account_id: Account ID for VIP list lookup (optional)

    Returns:
        True if all conditions match, False otherwise
    """
    if not conditions:
        return True

    # Check if we need VIP list
    needs_vip = any(
        c.operator == ConditionOperator.IN_VIP_LIST for c in conditions
    )
    vip_emails = get_vip_emails(account_id) if needs_vip and account_id else None

    for condition in conditions:
        if not match_condition(condition, event_data, vip_emails):
            return False

    return True


def prepare_email_event_data(email: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare email data for condition matching.

    Extracts and computes derived fields for easier matching.

    Args:
        email: Raw email data dictionary

    Returns:
        Enriched event data dictionary
    """
    event_data = email.copy()

    # Extract sender info
    sender = email.get("sender") or {}
    if isinstance(sender, dict):
        event_data["from_address"] = sender.get("address", "")
        event_data["from_name"] = sender.get("name", "")
        address = sender.get("address", "")
        event_data["from_domain"] = address.split("@")[-1] if "@" in address else ""
    elif isinstance(sender, str):
        event_data["from_address"] = sender
        event_data["from_domain"] = sender.split("@")[-1] if "@" in sender else ""
        event_data["from_name"] = ""

    # Count recipients
    event_data["to_count"] = len(email.get("to", []))
    event_data["cc_count"] = len(email.get("cc", []))

    # Detect reply/forward
    subject = email.get("subject", "")
    event_data["is_reply"] = subject.lower().startswith("re:")
    event_data["is_forward"] = subject.lower().startswith(("fwd:", "fw:"))

    # Calculate age
    received_at = email.get("received_at")
    if received_at:
        if isinstance(received_at, str):
            received_at = datetime.fromisoformat(received_at)
        age_delta = datetime.now() - received_at
        event_data["age_hours"] = age_delta.total_seconds() / 3600
    else:
        event_data["age_hours"] = 0

    return event_data


def prepare_calendar_event_data(event: dict[str, Any]) -> dict[str, Any]:
    """
    Prepare calendar event data for condition matching.

    Extracts and computes derived fields for easier matching.

    Args:
        event: Raw calendar event data dictionary

    Returns:
        Enriched event data dictionary
    """
    event_data = event.copy()

    # Extract organizer info
    organizer = event.get("organizer") or {}
    if isinstance(organizer, dict):
        event_data["organizer"] = organizer.get("email", "")
        email = organizer.get("email", "")
        event_data["organizer_domain"] = email.split("@")[-1] if "@" in email else ""
    elif isinstance(organizer, str):
        event_data["organizer"] = organizer
        event_data["organizer_domain"] = (
            organizer.split("@")[-1] if "@" in organizer else ""
        )

    # Count attendees
    event_data["attendee_count"] = len(event.get("attendees", []))

    # Calculate duration
    start_time = event.get("start_time")
    end_time = event.get("end_time")
    if start_time and end_time:
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        delta = end_time - start_time
        event_data["duration_minutes"] = int(delta.total_seconds() / 60)
    else:
        event_data["duration_minutes"] = 0

    # Extract time of day and day of week
    if start_time:
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        event_data["time_of_day"] = start_time.hour
        event_data["day_of_week"] = start_time.weekday()  # 0=Monday
    else:
        event_data["time_of_day"] = 0
        event_data["day_of_week"] = 0

    return event_data


def run_self_tests() -> None:
    """Run self-tests for the matcher module."""
    print("Testing policy matcher...")

    # Test extract_field_value
    data = {
        "subject": "Hello World",
        "sender": {"address": "test@example.com", "name": "Test User"},
        "labels": ["inbox", "important"],
    }
    assert extract_field_value("subject", data) == "Hello World"
    assert extract_field_value("sender.address", data) == "test@example.com"
    assert extract_field_value("sender.name", data) == "Test User"
    assert extract_field_value("nonexistent", data) is None
    assert extract_field_value("sender.nonexistent", data) is None

    # Test EQUALS operator
    cond = PolicyCondition("subject", ConditionOperator.EQUALS, "Hello World")
    assert match_condition(cond, data)
    cond = PolicyCondition("subject", ConditionOperator.EQUALS, "hello world")
    assert match_condition(cond, data)
    cond = PolicyCondition("subject", ConditionOperator.EQUALS, "Goodbye")
    assert not match_condition(cond, data)

    # Test CONTAINS operator
    cond = PolicyCondition("subject", ConditionOperator.CONTAINS, "World")
    assert match_condition(cond, data)
    cond = PolicyCondition("labels", ConditionOperator.CONTAINS, "inbox")
    assert match_condition(cond, data)
    cond = PolicyCondition("labels", ConditionOperator.CONTAINS, "spam")
    assert not match_condition(cond, data)

    # Test STARTS_WITH / ENDS_WITH
    cond = PolicyCondition("subject", ConditionOperator.STARTS_WITH, "Hello")
    assert match_condition(cond, data)
    cond = PolicyCondition("subject", ConditionOperator.ENDS_WITH, "World")
    assert match_condition(cond, data)

    # Test MATCHES_REGEX
    cond = PolicyCondition("subject", ConditionOperator.MATCHES_REGEX, r"Hello\s+\w+")
    assert match_condition(cond, data)
    cond = PolicyCondition("subject", ConditionOperator.MATCHES_REGEX, r"^\d+$")
    assert not match_condition(cond, data)

    # Test GREATER_THAN / LESS_THAN
    num_data = {"count": 10, "score": 85.5}
    cond = PolicyCondition("count", ConditionOperator.GREATER_THAN, 5)
    assert match_condition(cond, num_data)
    cond = PolicyCondition("count", ConditionOperator.LESS_THAN, 5)
    assert not match_condition(cond, num_data)
    cond = PolicyCondition("score", ConditionOperator.GREATER_THAN, 80)
    assert match_condition(cond, num_data)

    # Test IN_LIST / NOT_IN_LIST
    cond = PolicyCondition(
        "sender.address",
        ConditionOperator.IN_LIST,
        ["test@example.com", "admin@example.com"],
    )
    assert match_condition(cond, data)
    cond = PolicyCondition(
        "sender.address",
        ConditionOperator.NOT_IN_LIST,
        ["spam@example.com"],
    )
    assert match_condition(cond, data)

    # Test IS_EMPTY
    empty_data = {"subject": "", "labels": [], "missing": None}
    cond = PolicyCondition("subject", ConditionOperator.IS_EMPTY, None)
    assert match_condition(cond, empty_data)
    cond = PolicyCondition("labels", ConditionOperator.IS_EMPTY, None)
    assert match_condition(cond, empty_data)
    cond = PolicyCondition("missing", ConditionOperator.IS_EMPTY, None)
    assert match_condition(cond, empty_data)

    # Test match_all_conditions
    conditions = [
        PolicyCondition("subject", ConditionOperator.CONTAINS, "Hello"),
        PolicyCondition("sender.address", ConditionOperator.ENDS_WITH, "@example.com"),
    ]
    assert match_all_conditions(conditions, data)

    conditions.append(PolicyCondition("labels", ConditionOperator.CONTAINS, "spam"))
    assert not match_all_conditions(conditions, data)

    # Test prepare_email_event_data
    email = {
        "subject": "Re: Meeting tomorrow",
        "sender": {"address": "boss@company.com", "name": "Boss"},
        "to": [{"address": "me@example.com"}],
        "cc": [{"address": "team@example.com"}, {"address": "pm@example.com"}],
        "received_at": datetime.now().isoformat(),
    }
    prepared = prepare_email_event_data(email)
    assert prepared["from_address"] == "boss@company.com"
    assert prepared["from_domain"] == "company.com"
    assert prepared["to_count"] == 1
    assert prepared["cc_count"] == 2
    assert prepared["is_reply"] is True
    assert prepared["is_forward"] is False
    assert prepared["age_hours"] < 1

    # Test prepare_calendar_event_data
    event = {
        "title": "Team Standup",
        "organizer": {"email": "manager@company.com"},
        "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}],
        "start_time": datetime.now().replace(hour=10).isoformat(),
        "end_time": datetime.now().replace(hour=11).isoformat(),
        "is_recurring": True,
    }
    prepared = prepare_calendar_event_data(event)
    assert prepared["organizer"] == "manager@company.com"
    assert prepared["organizer_domain"] == "company.com"
    assert prepared["attendee_count"] == 2
    assert prepared["duration_minutes"] == 60
    assert prepared["time_of_day"] == 10

    print("OK: All policy matcher tests passed")


def main() -> int:
    """
    CLI entry point for testing condition matching.

    Usage:
        # Test a single condition
        python matcher.py --condition '{"field": "from_domain", "operator": "equals", "value": "example.com"}' --data '{"from_domain": "example.com"}'

        # Test multiple conditions
        python matcher.py --conditions '[{"field": "from_domain", "operator": "equals", "value": "example.com"}]' --data '{"from_domain": "example.com"}'

        # Run self-tests
        python matcher.py --test

        # Prepare email data
        python matcher.py --prepare-email '{"subject": "Re: Test", "sender": {"address": "test@example.com"}}'

    Returns:
        0 on success, 1 on failure
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Test policy condition matching against event data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test single condition match
  python matcher.py --condition '{"field": "from_domain", "operator": "equals", "value": "example.com"}' --data '{"from_domain": "example.com"}'

  # Test multiple conditions (AND logic)
  python matcher.py --conditions '[{"field": "from_domain", "operator": "equals", "value": "example.com"}, {"field": "subject", "operator": "contains", "value": "urgent"}]' --data '{"from_domain": "example.com", "subject": "URGENT: Please review"}'

  # Prepare raw email data for matching
  python matcher.py --prepare-email '{"subject": "Re: Test", "sender": {"address": "test@example.com"}}'

  # Prepare calendar event data for matching
  python matcher.py --prepare-calendar '{"title": "Meeting", "organizer": {"email": "boss@company.com"}, "start_time": "2025-01-15T10:00:00", "end_time": "2025-01-15T11:00:00"}'

  # Run self-tests
  python matcher.py --test
        """,
    )

    parser.add_argument(
        "--condition",
        type=str,
        help="Single condition JSON: {field, operator, value}",
    )
    parser.add_argument(
        "--conditions",
        type=str,
        help="Multiple conditions JSON array: [{field, operator, value}, ...]",
    )
    parser.add_argument(
        "--data",
        type=str,
        help="Event data JSON to match against",
    )
    parser.add_argument(
        "--account-id",
        type=str,
        help="Account ID for VIP list lookup (optional)",
    )
    parser.add_argument(
        "--prepare-email",
        type=str,
        help="Prepare raw email JSON for condition matching",
    )
    parser.add_argument(
        "--prepare-calendar",
        type=str,
        help="Prepare raw calendar event JSON for condition matching",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-tests",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Run self-tests
    if args.test:
        run_self_tests()
        return 0

    # Prepare email data
    if args.prepare_email:
        try:
            email_data = json.loads(args.prepare_email)
            prepared = prepare_email_event_data(email_data)
            if args.json:
                print(json.dumps(prepared, indent=2, default=str))
            else:
                print("Prepared email event data:")
                for key, value in prepared.items():
                    print(f"  {key}: {value}")
            return 0
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON for --prepare-email: {e}", file=sys.stderr)
            return 1

    # Prepare calendar data
    if args.prepare_calendar:
        try:
            calendar_data = json.loads(args.prepare_calendar)
            prepared = prepare_calendar_event_data(calendar_data)
            if args.json:
                print(json.dumps(prepared, indent=2, default=str))
            else:
                print("Prepared calendar event data:")
                for key, value in prepared.items():
                    print(f"  {key}: {value}")
            return 0
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON for --prepare-calendar: {e}", file=sys.stderr)
            return 1

    # Single condition match
    if args.condition:
        if not args.data:
            print("Error: --data is required with --condition", file=sys.stderr)
            return 1

        try:
            condition_dict = json.loads(args.condition)
            event_data = json.loads(args.data)

            condition = PolicyCondition.from_dict(condition_dict)
            result = match_condition(condition, event_data)

            if args.json:
                output = {
                    "match": result,
                    "condition": condition.to_dict(),
                    "data": event_data,
                }
                print(json.dumps(output, indent=2))
            else:
                status = "MATCH" if result else "NO MATCH"
                print(f"Result: {status}")
                print(f"  Field: {condition.field}")
                print(f"  Operator: {condition.operator.value}")
                print(f"  Expected: {condition.value}")
                print(f"  Actual: {extract_field_value(condition.field, event_data)}")

            return 0 if result else 1

        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Multiple conditions match
    if args.conditions:
        if not args.data:
            print("Error: --data is required with --conditions", file=sys.stderr)
            return 1

        try:
            conditions_list = json.loads(args.conditions)
            event_data = json.loads(args.data)

            conditions = [PolicyCondition.from_dict(c) for c in conditions_list]
            result = match_all_conditions(conditions, event_data, args.account_id)

            if args.json:
                individual_results = []
                for cond in conditions:
                    individual_results.append({
                        "condition": cond.to_dict(),
                        "match": match_condition(cond, event_data),
                    })
                output = {
                    "match": result,
                    "conditions_count": len(conditions),
                    "individual_results": individual_results,
                }
                print(json.dumps(output, indent=2))
            else:
                status = "ALL MATCH" if result else "NOT ALL MATCH"
                print(f"Result: {status}")
                print(f"Conditions evaluated: {len(conditions)}")
                for i, cond in enumerate(conditions, 1):
                    cond_result = match_condition(cond, event_data)
                    cond_status = "MATCH" if cond_result else "FAIL"
                    print(f"  {i}. [{cond_status}] {cond.field} {cond.operator.value} {cond.value}")

            return 0 if result else 1

        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # No action specified, show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
