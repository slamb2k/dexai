"""Default Policy Templates — Sensible defaults users can import and enable

This module provides pre-built policy templates that cover common automation
scenarios. Users can import these templates into their account and customize
them as needed.

Philosophy:
    ADHD users benefit from automation that "just works" out of the box.
    These templates encode best practices for email and calendar management,
    providing a starting point that can be customized over time.

Usage:
    # Get all default policies
    from tools.office.policies.defaults import get_default_policies
    policies = get_default_policies()

    # Get a specific policy by name
    from tools.office.policies.defaults import get_policy_by_name
    policy = get_policy_by_name("Archive Old Newsletters")

    # Get policies by type
    from tools.office.policies.defaults import get_policies_by_type
    inbox_policies = get_policies_by_type("inbox")

    # Import a default policy for an account
    from tools.office.policies.defaults import import_default_policy
    import_default_policy(account_id, "VIP Immediate Notify")

Safety:
    All default policies are disabled by default. Users must explicitly
    enable them after review to prevent unexpected automation.
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office.policies import (
    Policy,
    PolicyAction,
    PolicyCondition,
    get_connection,
)


# Default policy templates
# All policies are disabled by default for safety
DEFAULT_POLICIES: list[dict[str, Any]] = [
    {
        "name": "Archive Old Newsletters",
        "description": "Auto-archive unread newsletters after 7 days",
        "policy_type": "inbox",
        "conditions": [
            {
                "field": "from_domain",
                "operator": "in_list",
                "value": [
                    "substack.com",
                    "mailchimp.com",
                    "convertkit.com",
                    "buttondown.email",
                    "beehiiv.com",
                    "newsletter.com",
                ],
            },
            {"field": "is_read", "operator": "equals", "value": False},
            {"field": "age_hours", "operator": "greater_than", "value": 168},
        ],
        "actions": [{"action_type": "archive"}],
        "priority": 10,
        "enabled": False,
    },
    {
        "name": "VIP Immediate Notify",
        "description": "Always notify immediately for VIP contacts",
        "policy_type": "inbox",
        "conditions": [
            {"field": "from_address", "operator": "in_vip_list", "value": True}
        ],
        "actions": [
            {"action_type": "notify_immediately"},
            {"action_type": "ignore_flow_state"},
            {"action_type": "star"},
        ],
        "priority": 100,
        "enabled": False,
    },
    {
        "name": "Protect Focus Time",
        "description": "Auto-decline meetings during focus blocks",
        "policy_type": "calendar",
        "conditions": [
            {"field": "conflicts_with", "operator": "contains", "value": "focus_block"},
            {"field": "organizer", "operator": "in_vip_list", "value": False},
        ],
        "actions": [
            {"action_type": "decline"},
            {"action_type": "suggest_alternative", "parameters": {"days_ahead": 7}},
        ],
        "priority": 50,
        "enabled": False,
    },
    {
        "name": "Auto-Accept Team Meetings",
        "description": "Auto-accept recurring team meetings with no conflicts",
        "policy_type": "calendar",
        "conditions": [
            {"field": "organizer_domain", "operator": "equals", "value": "$user_domain"},
            {"field": "is_recurring", "operator": "equals", "value": True},
            {"field": "conflicts_with", "operator": "is_empty", "value": True},
        ],
        "actions": [{"action_type": "accept"}],
        "priority": 30,
        "enabled": False,
    },
    {
        "name": "Vacation Auto-Reply",
        "description": "Send vacation response (enable when on vacation)",
        "policy_type": "response",
        "conditions": [
            {"field": "is_first_contact_today", "operator": "equals", "value": True}
        ],
        "actions": [
            {"action_type": "auto_reply", "parameters": {"template": "vacation"}}
        ],
        "enabled": False,
        "priority": 100,
    },
    {
        "name": "Mark Promotional as Read",
        "description": "Auto-mark promotional emails as read",
        "policy_type": "inbox",
        "conditions": [
            {"field": "labels", "operator": "contains", "value": "PROMOTIONS"}
        ],
        "actions": [{"action_type": "mark_read"}],
        "priority": 5,
        "enabled": False,
    },
    {
        "name": "Digest Social Notifications",
        "description": "Suppress immediate notifications for social updates",
        "policy_type": "inbox",
        "conditions": [
            {
                "field": "from_domain",
                "operator": "in_list",
                "value": [
                    "linkedin.com",
                    "twitter.com",
                    "x.com",
                    "facebook.com",
                    "instagram.com",
                    "github.com",
                ],
            }
        ],
        "actions": [
            {"action_type": "suppress"},
            {"action_type": "notify_digest"},
        ],
        "priority": 20,
        "enabled": False,
    },
    {
        "name": "Star Long Threads",
        "description": "Star email threads with 5+ messages for follow-up",
        "policy_type": "inbox",
        "conditions": [
            {"field": "thread_message_count", "operator": "greater_than", "value": 5},
            {"field": "is_read", "operator": "equals", "value": False},
        ],
        "actions": [{"action_type": "star"}],
        "priority": 15,
        "enabled": False,
    },
    {
        "name": "Archive Old Notifications",
        "description": "Auto-archive notification emails older than 3 days",
        "policy_type": "inbox",
        "conditions": [
            {"field": "subject", "operator": "matches_regex", "value": "^\\[.*\\]|notification|alert"},
            {"field": "age_hours", "operator": "greater_than", "value": 72},
            {"field": "is_read", "operator": "equals", "value": True},
        ],
        "actions": [{"action_type": "archive"}],
        "priority": 5,
        "enabled": False,
    },
    {
        "name": "Decline After Hours",
        "description": "Auto-decline meetings outside business hours (9-5)",
        "policy_type": "calendar",
        "conditions": [
            {"field": "time_of_day", "operator": "less_than", "value": 9},
            {"field": "organizer", "operator": "in_vip_list", "value": False},
        ],
        "actions": [
            {"action_type": "decline"},
            {"action_type": "suggest_alternative", "parameters": {"prefer_morning": True}},
        ],
        "priority": 40,
        "enabled": False,
    },
    {
        "name": "Decline After Hours Evening",
        "description": "Auto-decline meetings after 5 PM",
        "policy_type": "calendar",
        "conditions": [
            {"field": "time_of_day", "operator": "greater_than", "value": 17},
            {"field": "organizer", "operator": "in_vip_list", "value": False},
        ],
        "actions": [
            {"action_type": "decline"},
            {"action_type": "suggest_alternative", "parameters": {"prefer_afternoon": True}},
        ],
        "priority": 40,
        "enabled": False,
    },
    {
        "name": "Label External Emails",
        "description": "Label emails from external domains",
        "policy_type": "inbox",
        "conditions": [
            {"field": "from_domain", "operator": "not_equals", "value": "$user_domain"}
        ],
        "actions": [
            {"action_type": "label", "parameters": {"label": "External"}}
        ],
        "priority": 1,
        "enabled": False,
    },
]


def get_default_policies() -> list[dict[str, Any]]:
    """
    Return list of default policy templates.

    Returns a deep copy to prevent accidental modification of the originals.

    Returns:
        List of policy template dictionaries
    """
    import copy
    return copy.deepcopy(DEFAULT_POLICIES)


def get_policy_by_name(name: str) -> dict[str, Any] | None:
    """
    Get a specific default policy by name.

    Args:
        name: The name of the policy to retrieve

    Returns:
        Policy dictionary if found, None otherwise
    """
    import copy
    for policy in DEFAULT_POLICIES:
        if policy["name"] == name:
            return copy.deepcopy(policy)
    return None


def get_policies_by_type(policy_type: str) -> list[dict[str, Any]]:
    """
    Get all default policies of a specific type.

    Args:
        policy_type: The policy type to filter by (inbox, calendar, response)

    Returns:
        List of matching policy template dictionaries
    """
    import copy
    return [
        copy.deepcopy(p)
        for p in DEFAULT_POLICIES
        if p["policy_type"] == policy_type
    ]


def get_policy_names() -> list[str]:
    """
    Get a list of all default policy names.

    Returns:
        List of policy names
    """
    return [p["name"] for p in DEFAULT_POLICIES]


def import_default_policy(
    account_id: str,
    policy_name: str,
    enabled: bool = False,
) -> dict[str, Any]:
    """
    Import a default policy into an account's policy list.

    Creates a new policy in the database based on the default template.
    The policy is disabled by default unless explicitly enabled.

    Args:
        account_id: The account to import the policy for
        policy_name: Name of the default policy to import
        enabled: Whether to enable the policy immediately (default False)

    Returns:
        {"success": bool, "policy_id": str | None, "error": str | None}
    """
    template = get_policy_by_name(policy_name)
    if not template:
        return {
            "success": False,
            "policy_id": None,
            "error": f"Unknown policy: {policy_name}",
        }

    policy_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO office_policies (
                id, account_id, name, description, policy_type,
                conditions, actions, enabled, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy_id,
                account_id,
                template["name"],
                template.get("description", ""),
                template["policy_type"],
                json.dumps(template["conditions"]),
                json.dumps(template["actions"]),
                enabled,
                template.get("priority", 0),
                now,
            ),
        )
        conn.commit()
        return {"success": True, "policy_id": policy_id, "error": None}
    except Exception as e:
        conn.rollback()
        return {"success": False, "policy_id": None, "error": str(e)}
    finally:
        conn.close()


def import_all_default_policies(
    account_id: str,
    enabled: bool = False,
) -> dict[str, Any]:
    """
    Import all default policies into an account.

    Creates all default policies in the database. Policies are disabled
    by default unless explicitly enabled.

    Args:
        account_id: The account to import policies for
        enabled: Whether to enable policies immediately (default False)

    Returns:
        {
            "success": bool,
            "imported": int,
            "failed": int,
            "errors": list[str]
        }
    """
    imported = 0
    failed = 0
    errors: list[str] = []

    for policy in DEFAULT_POLICIES:
        result = import_default_policy(account_id, policy["name"], enabled)
        if result["success"]:
            imported += 1
        else:
            failed += 1
            errors.append(f"{policy['name']}: {result['error']}")

    return {
        "success": failed == 0,
        "imported": imported,
        "failed": failed,
        "errors": errors,
    }


def list_default_policies_summary() -> list[dict[str, str]]:
    """
    Get a summary of all default policies for display.

    Returns:
        List of dictionaries with name, description, and type
    """
    return [
        {
            "name": p["name"],
            "description": p.get("description", ""),
            "type": p["policy_type"],
            "priority": p.get("priority", 0),
        }
        for p in DEFAULT_POLICIES
    ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Default Policy Templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all default policies
  python defaults.py --list

  # Show a specific policy
  python defaults.py --show "Archive Old Newsletters"

  # Import a policy for an account
  python defaults.py --import "VIP Immediate Notify" --account-id abc123

  # Import all policies for an account
  python defaults.py --import-all --account-id abc123
        """,
    )

    parser.add_argument("--list", action="store_true", help="List all default policies")
    parser.add_argument("--show", metavar="NAME", help="Show a specific policy")
    parser.add_argument("--import", dest="import_policy", metavar="NAME", help="Import a policy")
    parser.add_argument("--import-all", action="store_true", help="Import all policies")
    parser.add_argument("--account-id", help="Account ID for import operations")
    parser.add_argument("--enabled", action="store_true", help="Enable imported policies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list:
        policies = list_default_policies_summary()
        if args.json:
            print(json.dumps(policies, indent=2))
        else:
            print(f"Default Policies ({len(policies)} available):\n")
            for p in policies:
                print(f"  [{p['type']}] {p['name']} (priority: {p['priority']})")
                print(f"    {p['description']}")
                print()
        sys.exit(0)

    if args.show:
        policy = get_policy_by_name(args.show)
        if policy:
            if args.json:
                print(json.dumps(policy, indent=2))
            else:
                print(f"Policy: {policy['name']}")
                print(f"Type: {policy['policy_type']}")
                print(f"Description: {policy.get('description', 'N/A')}")
                print(f"Priority: {policy.get('priority', 0)}")
                print(f"Enabled by default: {policy.get('enabled', False)}")
                print("\nConditions:")
                for c in policy["conditions"]:
                    print(f"  - {c['field']} {c['operator']} {c['value']}")
                print("\nActions:")
                for a in policy["actions"]:
                    params = a.get("parameters", {})
                    params_str = f" ({params})" if params else ""
                    print(f"  - {a['action_type']}{params_str}")
            sys.exit(0)
        else:
            print(f"Error: Policy not found: {args.show}")
            sys.exit(1)

    if args.import_policy or args.import_all:
        if not args.account_id:
            print("Error: --account-id is required for import operations")
            sys.exit(1)

        if args.import_all:
            result = import_all_default_policies(args.account_id, args.enabled)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Imported: {result['imported']}")
                print(f"Failed: {result['failed']}")
                if result["errors"]:
                    print("Errors:")
                    for err in result["errors"]:
                        print(f"  - {err}")
            sys.exit(0 if result["success"] else 1)
        else:
            result = import_default_policy(
                args.account_id, args.import_policy, args.enabled
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                if result["success"]:
                    print(f"OK: Imported policy with ID {result['policy_id']}")
                else:
                    print(f"Error: {result['error']}")
            sys.exit(0 if result["success"] else 1)

    # Default: run self-tests
    print("Testing default policies module...")

    # Test get_default_policies
    policies = get_default_policies()
    assert len(policies) > 0
    assert all("name" in p for p in policies)
    assert all("conditions" in p for p in policies)
    assert all("actions" in p for p in policies)

    # Test get_policy_by_name
    policy = get_policy_by_name("VIP Immediate Notify")
    assert policy is not None
    assert policy["name"] == "VIP Immediate Notify"
    assert policy["policy_type"] == "inbox"

    missing = get_policy_by_name("Nonexistent Policy")
    assert missing is None

    # Test get_policies_by_type
    inbox_policies = get_policies_by_type("inbox")
    assert len(inbox_policies) > 0
    assert all(p["policy_type"] == "inbox" for p in inbox_policies)

    calendar_policies = get_policies_by_type("calendar")
    assert len(calendar_policies) > 0
    assert all(p["policy_type"] == "calendar" for p in calendar_policies)

    # Test get_policy_names
    names = get_policy_names()
    assert "VIP Immediate Notify" in names
    assert "Archive Old Newsletters" in names

    # Test list_default_policies_summary
    summary = list_default_policies_summary()
    assert len(summary) == len(DEFAULT_POLICIES)
    assert all("name" in s and "description" in s and "type" in s for s in summary)

    # Test that all policies are disabled by default
    for policy in DEFAULT_POLICIES:
        assert policy.get("enabled") is False, f"Policy {policy['name']} should be disabled by default"

    print("OK: All default policies tests passed")
    sys.exit(0)
