"""
Tool: Action Validator
Purpose: Validate actions before queuing for Level 4+ Managed Proxy integration

This module ensures that actions meet all requirements before being queued:
- Account has sufficient integration level (Level 4+)
- Rate limits are not exceeded (configurable per action type)
- Recipients are validated for safety
- Email content passes sentiment analysis

ADHD users benefit from these checks to prevent impulsive actions they may
later regret. Warnings provide gentle friction without blocking legitimate use.

Usage:
    # Validate a send_email action
    python validator.py --account-id abc123 --action-type send_email --data '{"to": ["user@example.com"]}'

    # Check rate limits only
    python validator.py --account-id abc123 --action-type send_email --check-rate-limit

    # Check recipient safety only
    python validator.py --check-recipients "user1@a.com,user2@b.com"

Dependencies:
    - sqlite3 (database access)
    - yaml (config loading)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.actions import ActionType
from tools.office.models import IntegrationLevel


# Load configuration from args/office_integration.yaml
def load_config() -> dict[str, Any]:
    """Load office integration config from YAML."""
    config_path = PROJECT_ROOT / "args" / "office_integration.yaml"
    if config_path.exists():
        import yaml

        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


# Action type to minimum level mapping
ACTION_LEVEL_REQUIREMENTS: dict[str, IntegrationLevel] = {
    "send_email": IntegrationLevel.MANAGED_PROXY,
    "delete_email": IntegrationLevel.MANAGED_PROXY,
    "archive_email": IntegrationLevel.MANAGED_PROXY,
    "mark_read": IntegrationLevel.MANAGED_PROXY,
    "schedule_meeting": IntegrationLevel.MANAGED_PROXY,
    "cancel_meeting": IntegrationLevel.MANAGED_PROXY,
    "accept_meeting": IntegrationLevel.MANAGED_PROXY,
    "decline_meeting": IntegrationLevel.MANAGED_PROXY,
}

# Default rate limits per hour (can be overridden by config)
DEFAULT_RATE_LIMITS: dict[str, int] = {
    "send_email": 50,
    "delete_email": 100,
    "archive_email": 200,
    "mark_read": 500,
    "schedule_meeting": 20,
    "cancel_meeting": 20,
    "accept_meeting": 50,
    "decline_meeting": 50,
}

# External domain warning threshold
LARGE_RECIPIENT_THRESHOLD = 10


def get_rate_limits() -> dict[str, int]:
    """Get rate limits from config or use defaults."""
    config = load_config()
    security_config = config.get("office_integration", {}).get("security", {})
    rate_limit_config = security_config.get("rate_limits", {})

    limits = DEFAULT_RATE_LIMITS.copy()

    # Override with config values if present
    if "emails_per_hour" in rate_limit_config:
        limits["send_email"] = rate_limit_config["emails_per_hour"]
    if "calendar_changes_per_hour" in rate_limit_config:
        for calendar_action in [
            "schedule_meeting",
            "cancel_meeting",
            "accept_meeting",
            "decline_meeting",
        ]:
            limits[calendar_action] = rate_limit_config["calendar_changes_per_hour"]

    return limits


def get_account(account_id: str) -> dict | None:
    """Get account details from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def validate_action(
    account_id: str,
    action_type: str,
    action_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate an action before queuing.

    Performs comprehensive validation:
    1. Account exists and has correct integration level
    2. Action type is valid
    3. Rate limits are not exceeded
    4. Recipients are validated (for email actions)
    5. Content passes sentiment analysis (for email actions)

    Args:
        account_id: Office account ID
        action_type: Type of action to validate
        action_data: Action-specific data

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str],
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Get account
    account = get_account(account_id)
    if not account:
        return {
            "valid": False,
            "errors": [f"Account not found: {account_id}"],
            "warnings": [],
        }

    # Validate action type
    if not ActionType.is_valid(action_type):
        return {
            "valid": False,
            "errors": [
                f"Invalid action type: {action_type}. "
                f"Valid types: {ActionType.values()}"
            ],
            "warnings": [],
        }

    # Check integration level
    required_level = ACTION_LEVEL_REQUIREMENTS.get(action_type)
    if required_level is None:
        errors.append(f"No level requirement defined for: {action_type}")
    elif account["integration_level"] < required_level.value:
        errors.append(
            f"Action '{action_type}' requires Level {required_level.value} "
            f"({required_level.display_name}). Current level: {account['integration_level']}"
        )

    # Check rate limits
    rate_check = check_rate_limits(account_id, action_type)
    if not rate_check["allowed"]:
        errors.append(
            f"Rate limit exceeded for {action_type}. "
            f"Used {rate_check['used']}/{rate_check['limit']} in the last hour. "
            f"Reset at: {rate_check['reset_at']}"
        )
    elif rate_check["remaining"] <= 5:
        warnings.append(
            f"Approaching rate limit for {action_type}. "
            f"Only {rate_check['remaining']} actions remaining this hour."
        )

    # Email-specific validations
    if action_type == "send_email":
        # Check recipients
        recipients = action_data.get("to", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        cc = action_data.get("cc", [])
        bcc = action_data.get("bcc", [])
        all_recipients = list(recipients) + list(cc or []) + list(bcc or [])

        recipient_check = check_recipient_safety(all_recipients)
        if not recipient_check["safe"]:
            warnings.extend(recipient_check["warnings"])

        # Run sentiment analysis on email content
        subject = action_data.get("subject", "")
        body = action_data.get("body", "") or action_data.get("body_text", "")
        if subject or body:
            sentiment = analyze_email_sentiment(subject, body)
            if sentiment:
                if not sentiment.get("safe_to_send"):
                    score = sentiment.get("score", 0)
                    if score >= 0.7:
                        warnings.append(
                            "Email has significant emotional content. "
                            "Consider waiting before sending."
                        )
                    elif score >= 0.5:
                        warnings.append(
                            "Email shows signs of frustration. "
                            "Consider reviewing the tone."
                        )
                    else:
                        warnings.append(
                            "Email may come across more strongly than intended. "
                            "Consider softening the tone."
                        )

                    # Add specific flags to warnings
                    flags = sentiment.get("flags", [])
                    if "strong_negative" in flags:
                        warnings.append("Strong negative language detected.")
                    if "reactive_phrasing" in flags:
                        warnings.append("Reactive phrasing detected.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def analyze_email_sentiment(subject: str, body: str) -> dict[str, Any] | None:
    """
    Analyze email sentiment using the sentiment analysis tool.

    Args:
        subject: Email subject
        body: Email body

    Returns:
        Sentiment analysis result or None if analysis fails
    """
    try:
        from tools.office.email.sentiment import analyze_email_sentiment as analyze

        return analyze(subject, body)
    except ImportError:
        return None
    except Exception:
        return None


def check_rate_limits(account_id: str, action_type: str) -> dict[str, Any]:
    """
    Check if action is within rate limits.

    Args:
        account_id: Office account ID
        action_type: Type of action

    Returns:
        {
            "allowed": bool,
            "remaining": int,
            "reset_at": str,
            "limit": int,
            "used": int,
        }
    """
    limits = get_rate_limits()
    limit = limits.get(action_type, 100)
    one_hour_ago = datetime.now() - timedelta(hours=1)
    reset_at = datetime.now() + timedelta(hours=1)

    conn = get_connection()
    cursor = conn.cursor()

    # Count actions in the last hour (excluding undone actions)
    cursor.execute(
        """
        SELECT COUNT(*) FROM office_actions
        WHERE account_id = ?
          AND action_type = ?
          AND created_at > ?
          AND status != 'undone'
        """,
        (account_id, action_type, one_hour_ago.isoformat()),
    )
    count = cursor.fetchone()[0]
    conn.close()

    remaining = max(0, limit - count)

    return {
        "allowed": count < limit,
        "remaining": remaining,
        "reset_at": reset_at.isoformat(),
        "limit": limit,
        "used": count,
    }


def check_recipient_safety(recipients: list[str]) -> dict[str, Any]:
    """
    Check recipients for safety concerns.

    Validates:
    - Not too many recipients (distribution list detection)
    - Not too many different domains
    - No obvious distribution list addresses

    Args:
        recipients: List of email addresses

    Returns:
        {
            "safe": bool,
            "warnings": list[str],
        }
    """
    warnings: list[str] = []

    if not recipients:
        return {"safe": True, "warnings": []}

    # Check for large recipient list
    if len(recipients) > LARGE_RECIPIENT_THRESHOLD:
        warnings.append(
            f"Large recipient list ({len(recipients)} recipients). "
            "Consider if all recipients are necessary."
        )

    # Extract domains and check for external domains
    domains = set()
    for recipient in recipients:
        if "@" in recipient:
            domain = recipient.split("@")[-1].lower()
            domains.add(domain)

    # Check for multiple external domains
    if len(domains) > 3:
        warnings.append(
            f"Sending to {len(domains)} different domains. "
            "Verify all recipients are intended."
        )

    # Check for potentially risky patterns (distribution lists)
    risky_patterns = [
        "all@",
        "everyone@",
        "company@",
        "team@",
        "staff@",
        "department@",
        "group@",
        "list@",
    ]
    for recipient in recipients:
        lower_recipient = recipient.lower()
        for pattern in risky_patterns:
            if pattern in lower_recipient:
                warnings.append(
                    f"Recipient '{recipient}' appears to be a distribution list. "
                    "Confirm this is intentional."
                )
                break

    return {
        "safe": len(warnings) == 0,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Action Validator for Level 4+ Office Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a send_email action
  python validator.py --account-id abc123 --action-type send_email \\
      --data '{"to": ["user@example.com"], "subject": "Hello", "body": "Hi there"}'

  # Check rate limits
  python validator.py --account-id abc123 --action-type send_email --check-rate-limit

  # Check recipient safety
  python validator.py --check-recipients "user1@a.com,user2@b.com,user3@c.com"
        """,
    )

    parser.add_argument("--account-id", help="Office account ID")
    parser.add_argument("--action-type", help="Type of action to validate")
    parser.add_argument("--data", help="Action data as JSON string")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--validate", action="store_true", help="Validate action (default)"
    )
    actions.add_argument(
        "--check-rate-limit", action="store_true", help="Check rate limits only"
    )
    actions.add_argument(
        "--check-recipients",
        metavar="EMAILS",
        help="Check recipient safety (comma-separated)",
    )

    args = parser.parse_args()

    if args.check_recipients:
        recipients = [r.strip() for r in args.check_recipients.split(",")]
        result = check_recipient_safety(recipients)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["safe"]:
                print("OK: Recipients appear safe")
            else:
                print("WARNINGS:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")
        sys.exit(0 if result["safe"] else 1)

    if not args.account_id:
        print("Error: --account-id is required for validation")
        sys.exit(1)

    if args.check_rate_limit:
        if not args.action_type:
            print("Error: --action-type is required for rate limit check")
            sys.exit(1)
        result = check_rate_limits(args.account_id, args.action_type)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["allowed"]:
                print(
                    f"OK: {result['remaining']}/{result['limit']} actions remaining"
                )
            else:
                print(
                    f"BLOCKED: Rate limit exceeded. "
                    f"Used {result['used']}/{result['limit']}. "
                    f"Reset at {result['reset_at']}"
                )
        sys.exit(0 if result["allowed"] else 1)

    # Default: validate action
    if not args.action_type:
        print("Error: --action-type is required for validation")
        sys.exit(1)

    action_data = {}
    if args.data:
        action_data = json.loads(args.data)

    result = validate_action(args.account_id, args.action_type, action_data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["valid"]:
            print("OK: Action is valid")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")
        else:
            print("INVALID: Action failed validation")
            if result["errors"]:
                print("\nErrors:")
                for error in result["errors"]:
                    print(f"  - {error}")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
