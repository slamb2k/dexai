"""Policy Engine — Evaluate and execute policies for Level 5 Autonomous integration

This module provides the core policy evaluation engine. Given an incoming event
(email, calendar, schedule), it finds applicable policies, evaluates conditions,
and returns the actions to execute.

Usage:
    from tools.office.policies.engine import (
        evaluate_policies,
        execute_policy_actions,
        check_policy_constraints,
        get_applicable_policies,
    )

    # Evaluate policies for an incoming email
    result = await evaluate_policies(
        account_id="account-123",
        event_type="email",
        event_data={"from_address": "boss@company.com", "subject": "Urgent"},
    )

    # Execute the matched actions
    if result["actions"]:
        await execute_policy_actions(
            account_id="account-123",
            policy_id=result["matched_policies"][0]["id"],
            actions=result["actions"],
            event_data=event_data,
        )

CLI:
    python tools/office/policies/engine.py --evaluate --account-id <id> --type email --data '{"from_address": "test@example.com"}'
    python tools/office/policies/engine.py --check-constraints --policy-id <id>
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from tools.office import get_connection
from tools.office.policies import (
    ActionType,
    Policy,
    PolicyAction,
    PolicyCondition,
    PolicyType,
    ensure_policy_tables,
)
from tools.office.policies.matcher import (
    match_all_conditions,
    prepare_calendar_event_data,
    prepare_email_event_data,
)


def _log_policy_execution(
    account_id: str,
    policy_id: str,
    trigger_type: str,
    trigger_data: dict[str, Any],
    actions_taken: list[dict[str, Any]],
    result: str,
) -> str:
    """
    Log a policy execution to the database.

    Args:
        account_id: Account that owns the policy
        policy_id: Policy that was executed
        trigger_type: Type of event that triggered the policy
        trigger_data: Event data that triggered the policy
        actions_taken: List of actions that were executed
        result: Execution result (success, failed, skipped)

    Returns:
        Execution log ID
    """
    ensure_policy_tables()
    conn = get_connection()
    cursor = conn.cursor()

    execution_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO office_policy_executions
        (id, account_id, policy_id, trigger_type, trigger_data, actions_taken, result)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            execution_id,
            account_id,
            policy_id,
            trigger_type,
            json.dumps(trigger_data),
            json.dumps(actions_taken),
            result,
        ),
    )
    conn.commit()
    conn.close()

    return execution_id


def _get_execution_count_today(account_id: str, policy_id: str) -> int:
    """Get the number of times a policy has executed today."""
    ensure_policy_tables()
    conn = get_connection()
    cursor = conn.cursor()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    cursor.execute(
        """
        SELECT COUNT(*) as count FROM office_policy_executions
        WHERE account_id = ? AND policy_id = ? AND created_at >= ? AND result = 'success'
        """,
        (account_id, policy_id, today_start.isoformat()),
    )
    row = cursor.fetchone()
    conn.close()

    return row["count"] if row else 0


def _get_last_execution_time(account_id: str, policy_id: str) -> datetime | None:
    """Get the last execution time for a policy."""
    ensure_policy_tables()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT created_at FROM office_policy_executions
        WHERE account_id = ? AND policy_id = ? AND result = 'success'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (account_id, policy_id),
    )
    row = cursor.fetchone()
    conn.close()

    if row and row["created_at"]:
        return datetime.fromisoformat(row["created_at"])
    return None


async def check_policy_constraints(
    policy: Policy,
    account_id: str,
) -> dict[str, Any]:
    """
    Check if a policy can be executed based on its constraints.

    Verifies rate limits and cooldown periods.

    Args:
        policy: Policy to check
        account_id: Account ID for execution counts

    Returns:
        {"can_execute": bool, "reason": str | None}
    """
    # Check daily execution limit
    if policy.max_executions_per_day is not None:
        execution_count = _get_execution_count_today(account_id, policy.id)
        if execution_count >= policy.max_executions_per_day:
            return {
                "can_execute": False,
                "reason": f"Daily limit reached ({execution_count}/{policy.max_executions_per_day})",
            }

    # Check cooldown period
    if policy.cooldown_minutes is not None:
        last_execution = _get_last_execution_time(account_id, policy.id)
        if last_execution:
            cooldown_end = last_execution + timedelta(minutes=policy.cooldown_minutes)
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).total_seconds() / 60
                return {
                    "can_execute": False,
                    "reason": f"Cooldown active ({remaining:.1f} minutes remaining)",
                }

    return {"can_execute": True, "reason": None}


async def get_applicable_policies(
    account_id: str,
    event_type: str,
) -> list[Policy]:
    """
    Get all enabled policies for an account and event type, sorted by priority.

    Args:
        account_id: Account to get policies for
        event_type: Type of event (email, calendar, response, schedule)

    Returns:
        List of Policy objects sorted by priority (highest first)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_policies
        WHERE account_id = ? AND policy_type = ? AND enabled = TRUE
        ORDER BY priority DESC, created_at ASC
        """,
        (account_id, event_type),
    )
    rows = cursor.fetchall()
    conn.close()

    policies = []
    for row in rows:
        row_dict = dict(row)
        # Parse JSON fields
        if row_dict.get("conditions"):
            row_dict["conditions"] = json.loads(row_dict["conditions"])
        if row_dict.get("actions"):
            row_dict["actions"] = json.loads(row_dict["actions"])
        policies.append(Policy.from_dict(row_dict))

    return policies


async def evaluate_policies(
    account_id: str,
    event_type: str,
    event_data: dict[str, Any],
    match_all: bool = False,
) -> dict[str, Any]:
    """
    Evaluate policies against an incoming event.

    Finds all applicable policies, checks conditions, and returns
    the actions to execute.

    Args:
        account_id: Account to evaluate policies for
        event_type: Type of event (email, calendar, response, schedule)
        event_data: Event data dictionary
        match_all: If True, return all matching policies; if False, first match only

    Returns:
        {
            "matched_policies": list of matching policy dicts,
            "actions": list of action dicts to execute,
            "should_prompt": bool (True if novel situation),
        }
    """
    # Check if automation is paused
    from tools.office.automation.emergency import check_pause_status

    if check_pause_status(account_id):
        return {
            "matched_policies": [],
            "actions": [],
            "should_prompt": False,
            "paused": True,
            "message": "Automation is paused",
        }

    # Prepare event data based on type
    if event_type == "email":
        prepared_data = prepare_email_event_data(event_data)
    elif event_type == "calendar":
        prepared_data = prepare_calendar_event_data(event_data)
    else:
        prepared_data = event_data.copy()

    # Get applicable policies
    policies = await get_applicable_policies(account_id, event_type)

    if not policies:
        return {
            "matched_policies": [],
            "actions": [],
            "should_prompt": True,
            "message": "No policies defined for this event type",
        }

    matched_policies = []
    all_actions = []

    for policy in policies:
        # Check if all conditions match
        if match_all_conditions(policy.conditions, prepared_data, account_id):
            # Check execution constraints
            constraint_result = await check_policy_constraints(policy, account_id)

            if constraint_result["can_execute"]:
                matched_policies.append(policy.to_dict())
                all_actions.extend([a.to_dict() for a in policy.actions])

                # If not matching all, stop at first match
                if not match_all:
                    break

    # If no policies matched, suggest prompting user
    should_prompt = len(matched_policies) == 0

    return {
        "matched_policies": matched_policies,
        "actions": all_actions,
        "should_prompt": should_prompt,
    }


async def execute_policy_actions(
    account_id: str,
    policy_id: str,
    actions: list[dict[str, Any]],
    event_data: dict[str, Any],
    use_undo_window: bool = True,
) -> dict[str, Any]:
    """
    Execute actions from a matched policy.

    Routes actions through the action queue for undo capability.

    Args:
        account_id: Account executing the actions
        policy_id: Policy that triggered the actions
        actions: List of action dicts to execute
        event_data: Original event data
        use_undo_window: Whether to use undo window (default True)

    Returns:
        {"success": True, "results": list of action results}
    """
    from tools.office.actions.queue import queue_action

    results = []
    action_dicts = [a.to_dict() if hasattr(a, "to_dict") else a for a in actions]

    for action in action_dicts:
        action_type = action.get("action_type")
        parameters = action.get("parameters", {})

        # Map policy actions to queue action types
        action_mapping = {
            "archive": "archive_email",
            "delete": "delete_email",
            "mark_read": "mark_read_email",
            "star": "star_email",
            "label": "label_email",
            "forward": "forward_email",
            "auto_reply": "send_email",
            "accept": "accept_meeting",
            "decline": "decline_meeting",
            "tentative": "tentative_meeting",
            "suggest_alternative": "suggest_meeting_alternative",
        }

        queue_action_type = action_mapping.get(action_type)

        # Skip notification and special actions - handle separately
        if action_type in (
            "notify_immediately",
            "notify_digest",
            "suppress",
            "ignore_flow_state",
            "escalate",
        ):
            results.append({
                "action_type": action_type,
                "success": True,
                "skipped": True,
                "reason": "Notification/special action handled separately",
            })
            continue

        if not queue_action_type:
            results.append({
                "action_type": action_type,
                "success": False,
                "error": f"Unknown action type: {action_type}",
            })
            continue

        # Build action data
        action_data = {**event_data, **parameters}

        # Queue the action
        undo_window = 60 if use_undo_window else 0
        result = await queue_action(
            account_id=account_id,
            action_type=queue_action_type,
            action_data=action_data,
            undo_window_seconds=undo_window,
            priority="normal",
        )

        results.append({
            "action_type": action_type,
            "queue_action_type": queue_action_type,
            **result,
        })

    # Log the execution
    _log_policy_execution(
        account_id=account_id,
        policy_id=policy_id,
        trigger_type=event_data.get("_event_type", "unknown"),
        trigger_data=event_data,
        actions_taken=action_dicts,
        result="success" if all(r.get("success") for r in results) else "partial",
    )

    return {
        "success": True,
        "results": results,
        "execution_logged": True,
    }


async def get_policy_execution_history(
    account_id: str,
    policy_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get policy execution history.

    Args:
        account_id: Account to get history for
        policy_id: Optional filter by policy ID
        limit: Maximum number of records to return

    Returns:
        {"success": True, "executions": list}
    """
    ensure_policy_tables()
    conn = get_connection()
    cursor = conn.cursor()

    if policy_id:
        cursor.execute(
            """
            SELECT * FROM office_policy_executions
            WHERE account_id = ? AND policy_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account_id, policy_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM office_policy_executions
            WHERE account_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account_id, limit),
        )

    rows = cursor.fetchall()
    conn.close()

    executions = []
    for row in rows:
        execution = dict(row)
        if execution.get("trigger_data"):
            execution["trigger_data"] = json.loads(execution["trigger_data"])
        if execution.get("actions_taken"):
            execution["actions_taken"] = json.loads(execution["actions_taken"])
        executions.append(execution)

    return {"success": True, "executions": executions}


def main() -> None:
    """CLI entry point for the policy engine."""
    parser = argparse.ArgumentParser(
        description="Policy Evaluation Engine for Level 5 Office Integration"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate policies for an event")
    eval_parser.add_argument("--account-id", required=True, help="Account ID")
    eval_parser.add_argument(
        "--type",
        required=True,
        choices=["email", "calendar", "response", "schedule"],
        help="Event type",
    )
    eval_parser.add_argument(
        "--data",
        required=True,
        help="Event data as JSON string",
    )
    eval_parser.add_argument(
        "--match-all",
        action="store_true",
        help="Return all matching policies instead of first match",
    )

    # check-constraints command
    check_parser = subparsers.add_parser(
        "check-constraints",
        help="Check if a policy can be executed",
    )
    check_parser.add_argument("--policy-id", required=True, help="Policy ID")
    check_parser.add_argument("--account-id", required=True, help="Account ID")

    # history command
    history_parser = subparsers.add_parser(
        "history",
        help="Get policy execution history",
    )
    history_parser.add_argument("--account-id", required=True, help="Account ID")
    history_parser.add_argument("--policy-id", help="Filter by policy ID")
    history_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum records to return",
    )

    args = parser.parse_args()

    if args.command == "evaluate":
        event_data = json.loads(args.data)
        result = asyncio.run(
            evaluate_policies(
                account_id=args.account_id,
                event_type=args.type,
                event_data=event_data,
                match_all=args.match_all,
            )
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "check-constraints":
        # Get the policy first
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM office_policies WHERE id = ?",
            (args.policy_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            print(json.dumps({"success": False, "error": "Policy not found"}))
            sys.exit(1)

        row_dict = dict(row)
        if row_dict.get("conditions"):
            row_dict["conditions"] = json.loads(row_dict["conditions"])
        if row_dict.get("actions"):
            row_dict["actions"] = json.loads(row_dict["actions"])
        policy = Policy.from_dict(row_dict)

        result = asyncio.run(
            check_policy_constraints(policy, args.account_id)
        )
        print(json.dumps(result, indent=2))

    elif args.command == "history":
        result = asyncio.run(
            get_policy_execution_history(
                account_id=args.account_id,
                policy_id=args.policy_id,
                limit=args.limit,
            )
        )
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
