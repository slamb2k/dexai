"""Policy Manager — CRUD operations for Level 5 automation policies

This module provides management functions for creating, reading, updating,
and deleting automation policies. Policies define the rules for autonomous
email and calendar management.

Usage:
    from tools.office.policies.manager import (
        create_policy,
        get_policy,
        update_policy,
        delete_policy,
        list_policies,
        toggle_policy,
        import_default_policies,
        duplicate_policy,
        get_policy_stats,
    )

    # Create a new policy
    result = await create_policy(
        account_id="account-123",
        name="Archive Newsletters",
        policy_type="inbox",
        conditions=[{"field": "from_domain", "operator": "contains", "value": "newsletter"}],
        actions=[{"action_type": "archive"}],
    )

    # List all policies
    result = await list_policies(account_id="account-123")

CLI:
    python tools/office/policies/manager.py --account-id <id> --list
    python tools/office/policies/manager.py --account-id <id> --create --name "My Policy" --type inbox --conditions '[]' --actions '[]'
    python tools/office/policies/manager.py --account-id <id> --toggle <policy-id> --enabled true
    python tools/office/policies/manager.py --account-id <id> --import-defaults
    python tools/office/policies/manager.py --account-id <id> --stats <policy-id>
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office import get_connection
from tools.office.policies import (
    ActionType,
    ConditionOperator,
    Policy,
    PolicyAction,
    PolicyCondition,
    PolicyType,
    ensure_policy_tables,
)


async def create_policy(
    account_id: str,
    name: str,
    policy_type: str,
    conditions: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    description: str = "",
    priority: int = 0,
    enabled: bool = True,
    max_executions_per_day: int | None = None,
    cooldown_minutes: int | None = None,
    require_undo_window: bool = True,
) -> dict[str, Any]:
    """
    Create a new automation policy.

    Args:
        account_id: Account to create the policy for
        name: Human-readable policy name
        policy_type: Type of policy (inbox, calendar, response, schedule)
        conditions: List of condition dicts
        actions: List of action dicts
        description: Optional description
        priority: Priority level (higher = evaluated first)
        enabled: Whether the policy is active
        max_executions_per_day: Optional daily execution limit
        cooldown_minutes: Optional cooldown between executions
        require_undo_window: Whether actions need undo capability

    Returns:
        {"success": True, "policy_id": str}
    """
    # Validate policy type
    if policy_type not in PolicyType.values():
        return {
            "success": False,
            "error": f"Invalid policy type: {policy_type}. Valid types: {PolicyType.values()}",
        }

    # Validate conditions
    for cond in conditions:
        operator = cond.get("operator")
        if operator and operator not in ConditionOperator.values():
            return {
                "success": False,
                "error": f"Invalid condition operator: {operator}",
            }

    # Validate actions
    for action in actions:
        action_type = action.get("action_type")
        if action_type and action_type not in ActionType.values():
            return {
                "success": False,
                "error": f"Invalid action type: {action_type}",
            }

    conn = get_connection()
    cursor = conn.cursor()

    # Verify account exists
    cursor.execute(
        "SELECT id FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Account not found: {account_id}"}

    # Generate policy ID
    policy_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    cursor.execute(
        """
        INSERT INTO office_policies (
            id, account_id, name, policy_type, conditions, actions,
            enabled, priority, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            account_id,
            name,
            policy_type,
            json.dumps(conditions),
            json.dumps(actions),
            enabled,
            priority,
            now,
        ),
    )
    conn.commit()
    conn.close()

    # Ensure policy tables exist (for execution tracking)
    ensure_policy_tables()

    return {
        "success": True,
        "policy_id": policy_id,
        "name": name,
        "policy_type": policy_type,
        "enabled": enabled,
    }


async def get_policy(policy_id: str) -> dict[str, Any]:
    """
    Get a policy by ID.

    Args:
        policy_id: Policy ID to retrieve

    Returns:
        Policy dict or error
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_policies WHERE id = ?",
        (policy_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Policy not found: {policy_id}"}

    policy = dict(row)
    if policy.get("conditions"):
        policy["conditions"] = json.loads(policy["conditions"])
    if policy.get("actions"):
        policy["actions"] = json.loads(policy["actions"])

    return {"success": True, "policy": policy}


async def update_policy(
    policy_id: str,
    **updates: Any,
) -> dict[str, Any]:
    """
    Update a policy.

    Args:
        policy_id: Policy ID to update
        **updates: Fields to update (name, description, conditions, actions, etc.)

    Returns:
        {"success": True} or error
    """
    # Get existing policy
    result = await get_policy(policy_id)
    if not result.get("success"):
        return result

    conn = get_connection()
    cursor = conn.cursor()

    # Build update query
    allowed_fields = {
        "name",
        "description",
        "conditions",
        "actions",
        "enabled",
        "priority",
        "max_executions_per_day",
        "cooldown_minutes",
        "require_undo_window",
    }

    set_clauses = []
    params = []

    for field, value in updates.items():
        if field not in allowed_fields:
            continue

        # Serialize JSON fields
        if field in ("conditions", "actions"):
            value = json.dumps(value)

        set_clauses.append(f"{field} = ?")
        params.append(value)

    if not set_clauses:
        conn.close()
        return {"success": False, "error": "No valid fields to update"}

    params.append(policy_id)
    query = f"UPDATE office_policies SET {', '.join(set_clauses)} WHERE id = ?"

    cursor.execute(query, params)
    conn.commit()
    conn.close()

    return {"success": True, "policy_id": policy_id, "updated_fields": list(updates.keys())}


async def delete_policy(policy_id: str) -> dict[str, Any]:
    """
    Delete a policy.

    Args:
        policy_id: Policy ID to delete

    Returns:
        {"success": True} or error
    """
    # Verify policy exists
    result = await get_policy(policy_id)
    if not result.get("success"):
        return result

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM office_policies WHERE id = ?",
        (policy_id,),
    )
    conn.commit()
    conn.close()

    return {"success": True, "policy_id": policy_id, "deleted": True}


async def list_policies(
    account_id: str,
    policy_type: str | None = None,
    enabled_only: bool = False,
) -> dict[str, Any]:
    """
    List policies for an account.

    Args:
        account_id: Account to list policies for
        policy_type: Optional filter by policy type
        enabled_only: If True, only return enabled policies

    Returns:
        {"success": True, "policies": list}
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM office_policies WHERE account_id = ?"
    params: list[Any] = [account_id]

    if policy_type:
        query += " AND policy_type = ?"
        params.append(policy_type)

    if enabled_only:
        query += " AND enabled = TRUE"

    query += " ORDER BY priority DESC, created_at ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    policies = []
    for row in rows:
        policy = dict(row)
        if policy.get("conditions"):
            policy["conditions"] = json.loads(policy["conditions"])
        if policy.get("actions"):
            policy["actions"] = json.loads(policy["actions"])
        policies.append(policy)

    return {
        "success": True,
        "policies": policies,
        "count": len(policies),
    }


async def toggle_policy(policy_id: str, enabled: bool) -> dict[str, Any]:
    """
    Enable or disable a policy.

    Args:
        policy_id: Policy ID to toggle
        enabled: New enabled state

    Returns:
        {"success": True} or error
    """
    return await update_policy(policy_id, enabled=enabled)


async def import_default_policies(account_id: str) -> dict[str, Any]:
    """
    Import all default policy templates for an account.

    Default policies are imported as disabled so the user must
    explicitly enable them.

    Args:
        account_id: Account to import policies for

    Returns:
        {"success": True, "imported": int}
    """
    from tools.office.policies.defaults import DEFAULT_POLICIES

    imported = 0
    errors = []

    for policy_template in DEFAULT_POLICIES:
        result = await create_policy(
            account_id=account_id,
            name=policy_template["name"],
            policy_type=policy_template["policy_type"],
            conditions=policy_template["conditions"],
            actions=policy_template["actions"],
            description=policy_template.get("description", ""),
            priority=policy_template.get("priority", 0),
            enabled=policy_template.get("enabled", False),  # Default to disabled
        )

        if result.get("success"):
            imported += 1
        else:
            errors.append({
                "name": policy_template["name"],
                "error": result.get("error"),
            })

    return {
        "success": True,
        "imported": imported,
        "total": len(DEFAULT_POLICIES),
        "errors": errors if errors else None,
    }


async def duplicate_policy(policy_id: str, new_name: str) -> dict[str, Any]:
    """
    Duplicate an existing policy with a new name.

    Args:
        policy_id: Policy to duplicate
        new_name: Name for the new policy

    Returns:
        {"success": True, "policy_id": str} or error
    """
    # Get existing policy
    result = await get_policy(policy_id)
    if not result.get("success"):
        return result

    policy = result["policy"]

    # Create new policy with same settings
    return await create_policy(
        account_id=policy["account_id"],
        name=new_name,
        policy_type=policy["policy_type"],
        conditions=policy["conditions"],
        actions=policy["actions"],
        description=policy.get("description", "") + " (copy)",
        priority=policy.get("priority", 0),
        enabled=False,  # Start disabled
    )


async def get_policy_stats(policy_id: str) -> dict[str, Any]:
    """
    Get execution statistics for a policy.

    Args:
        policy_id: Policy to get stats for

    Returns:
        {
            "success": True,
            "execution_count": int,
            "last_execution": str | None,
            "success_rate": float,
        }
    """
    ensure_policy_tables()
    conn = get_connection()
    cursor = conn.cursor()

    # Total execution count
    cursor.execute(
        "SELECT COUNT(*) as count FROM office_policy_executions WHERE policy_id = ?",
        (policy_id,),
    )
    row = cursor.fetchone()
    total_count = row["count"] if row else 0

    # Successful execution count
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM office_policy_executions
        WHERE policy_id = ? AND result = 'success'
        """,
        (policy_id,),
    )
    row = cursor.fetchone()
    success_count = row["count"] if row else 0

    # Last execution
    cursor.execute(
        """
        SELECT created_at FROM office_policy_executions
        WHERE policy_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (policy_id,),
    )
    row = cursor.fetchone()
    last_execution = row["created_at"] if row else None

    # Executions today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cursor.execute(
        """
        SELECT COUNT(*) as count FROM office_policy_executions
        WHERE policy_id = ? AND created_at >= ?
        """,
        (policy_id, today_start.isoformat()),
    )
    row = cursor.fetchone()
    executions_today = row["count"] if row else 0

    conn.close()

    success_rate = (success_count / total_count * 100) if total_count > 0 else 0.0

    return {
        "success": True,
        "policy_id": policy_id,
        "execution_count": total_count,
        "success_count": success_count,
        "last_execution": last_execution,
        "success_rate": round(success_rate, 2),
        "executions_today": executions_today,
    }


def main() -> None:
    """CLI entry point for the policy manager."""
    parser = argparse.ArgumentParser(
        description="Policy Manager for Level 5 Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all policies
  python manager.py --account-id abc123 --list

  # Create a new policy
  python manager.py --account-id abc123 --create --name "My Policy" --type inbox \\
      --conditions '[{"field": "from_domain", "operator": "equals", "value": "example.com"}]' \\
      --actions '[{"action_type": "archive"}]'

  # Toggle a policy
  python manager.py --account-id abc123 --toggle policy-id --enabled true

  # Import default policies
  python manager.py --account-id abc123 --import-defaults

  # Get policy stats
  python manager.py --account-id abc123 --stats policy-id
        """,
    )

    parser.add_argument("--account-id", required=True, help="Office account ID")

    # Actions (mutually exclusive)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="List policies")
    actions.add_argument("--get", metavar="POLICY_ID", help="Get policy details")
    actions.add_argument("--create", action="store_true", help="Create a policy")
    actions.add_argument("--delete", metavar="POLICY_ID", help="Delete a policy")
    actions.add_argument("--toggle", metavar="POLICY_ID", help="Toggle policy enabled state")
    actions.add_argument("--import-defaults", action="store_true", help="Import default policies")
    actions.add_argument("--duplicate", metavar="POLICY_ID", help="Duplicate a policy")
    actions.add_argument("--stats", metavar="POLICY_ID", help="Get policy statistics")

    # Create options
    parser.add_argument("--name", help="Policy name (for create/duplicate)")
    parser.add_argument(
        "--type",
        choices=["inbox", "calendar", "response", "schedule"],
        help="Policy type (for create)",
    )
    parser.add_argument("--conditions", help="Conditions as JSON (for create)")
    parser.add_argument("--actions-json", dest="actions_data", help="Actions as JSON (for create)")
    parser.add_argument("--description", default="", help="Policy description")
    parser.add_argument("--priority", type=int, default=0, help="Policy priority")

    # Toggle option
    parser.add_argument(
        "--enabled",
        choices=["true", "false"],
        help="Enabled state (for toggle)",
    )

    # List filters
    parser.add_argument("--type-filter", help="Filter by policy type (for list)")
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only show enabled policies (for list)",
    )

    # Output format
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    result = None

    if args.list:
        result = asyncio.run(
            list_policies(
                account_id=args.account_id,
                policy_type=args.type_filter,
                enabled_only=args.enabled_only,
            )
        )

    elif args.get:
        result = asyncio.run(get_policy(args.get))

    elif args.create:
        if not all([args.name, args.type, args.conditions, args.actions_data]):
            parser.error("--create requires --name, --type, --conditions, and --actions-json")

        conditions = json.loads(args.conditions)
        actions_list = json.loads(args.actions_data)

        result = asyncio.run(
            create_policy(
                account_id=args.account_id,
                name=args.name,
                policy_type=args.type,
                conditions=conditions,
                actions=actions_list,
                description=args.description,
                priority=args.priority,
            )
        )

    elif args.delete:
        result = asyncio.run(delete_policy(args.delete))

    elif args.toggle:
        if not args.enabled:
            parser.error("--toggle requires --enabled")
        enabled = args.enabled.lower() == "true"
        result = asyncio.run(toggle_policy(args.toggle, enabled))

    elif args.import_defaults:
        result = asyncio.run(import_default_policies(args.account_id))

    elif args.duplicate:
        if not args.name:
            parser.error("--duplicate requires --name")
        result = asyncio.run(duplicate_policy(args.duplicate, args.name))

    elif args.stats:
        result = asyncio.run(get_policy_stats(args.stats))

    # Output result
    if result:
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("success"):
                print("OK")
                if args.list:
                    policies = result.get("policies", [])
                    print(f"Policies ({result.get('count', len(policies))}):")
                    for p in policies:
                        status = "enabled" if p.get("enabled") else "disabled"
                        print(f"  [{p['id'][:8]}] {p['name']} ({p['policy_type']}) - {status}")
                elif args.stats:
                    print(f"Policy: {result.get('policy_id', '')[:8]}")
                    print(f"Total executions: {result.get('execution_count', 0)}")
                    print(f"Success rate: {result.get('success_rate', 0)}%")
                    print(f"Last execution: {result.get('last_execution', 'Never')}")
                    print(f"Executions today: {result.get('executions_today', 0)}")
                elif args.import_defaults:
                    print(f"Imported: {result.get('imported', 0)}/{result.get('total', 0)}")
                else:
                    print(json.dumps(result, indent=2, default=str))
            else:
                print(f"ERROR: {result.get('error')}")
                sys.exit(1)


if __name__ == "__main__":
    main()
