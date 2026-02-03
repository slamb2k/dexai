"""
Tool: Level Detector
Purpose: Determine current integration level from granted OAuth scopes

Analyzes the scopes granted by a user to determine what integration
level their account is currently operating at. Also provides suggestions
for level upgrades when appropriate.

Usage:
    python tools/office/level_detector.py --account-id <id>
    python tools/office/level_detector.py --scopes "scope1 scope2" --provider google

Dependencies:
    - pyyaml (pip install pyyaml)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection  # noqa: E402
from tools.office.models import IntegrationLevel  # noqa: E402


# Scope requirements per level
GOOGLE_LEVEL_REQUIREMENTS = {
    IntegrationLevel.READ_ONLY: {
        "required": ["gmail.readonly", "calendar.readonly"],
        "any_of": [],
    },
    IntegrationLevel.COLLABORATIVE: {
        "required": ["gmail.modify", "calendar"],
        "any_of": [],
    },
    IntegrationLevel.MANAGED_PROXY: {
        "required": ["gmail.modify", "gmail.send", "calendar"],
        "any_of": [],
    },
    IntegrationLevel.AUTONOMOUS: {
        "required": ["gmail.modify", "gmail.send", "calendar", "contacts"],
        "any_of": [],
    },
}

MICROSOFT_LEVEL_REQUIREMENTS = {
    IntegrationLevel.READ_ONLY: {
        "required": ["Mail.Read", "Calendars.Read"],
        "any_of": [],
    },
    IntegrationLevel.COLLABORATIVE: {
        "required": ["Mail.ReadWrite", "Calendars.ReadWrite"],
        "any_of": [],
    },
    IntegrationLevel.MANAGED_PROXY: {
        "required": ["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite"],
        "any_of": [],
    },
    IntegrationLevel.AUTONOMOUS: {
        "required": ["Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite", "Contacts.ReadWrite"],
        "any_of": [],
    },
}


def normalize_google_scope(scope: str) -> str:
    """
    Normalize a Google OAuth scope to short form.

    'https://www.googleapis.com/auth/gmail.readonly' -> 'gmail.readonly'
    """
    if scope.startswith("https://www.googleapis.com/auth/"):
        return scope.replace("https://www.googleapis.com/auth/", "")
    return scope


def normalize_microsoft_scope(scope: str) -> str:
    """
    Normalize a Microsoft scope to standard form.

    Microsoft scopes are already in short form, but may have resource prefix.
    'https://graph.microsoft.com/Mail.Read' -> 'Mail.Read'
    """
    if "graph.microsoft.com/" in scope:
        return scope.split("/")[-1]
    return scope


def check_level_requirements(
    scopes: list[str],
    provider: str,
    level: IntegrationLevel,
) -> dict[str, Any]:
    """
    Check if scopes meet requirements for a specific level.

    Args:
        scopes: List of granted scopes
        provider: 'google' or 'microsoft'
        level: Level to check

    Returns:
        dict with meets_requirements, missing_scopes, extra_scopes
    """
    if level == IntegrationLevel.SANDBOXED:
        return {"meets_requirements": True, "missing_scopes": [], "extra_scopes": []}

    # Normalize scopes
    if provider == "google":
        normalized = [normalize_google_scope(s) for s in scopes]
        requirements = GOOGLE_LEVEL_REQUIREMENTS.get(level)
    elif provider == "microsoft":
        normalized = [normalize_microsoft_scope(s) for s in scopes]
        requirements = MICROSOFT_LEVEL_REQUIREMENTS.get(level)
    else:
        return {"meets_requirements": False, "error": f"Unknown provider: {provider}"}

    if not requirements:
        return {"meets_requirements": False, "error": f"Unknown level: {level}"}

    # Check required scopes
    missing = []
    for required in requirements["required"]:
        # Case-insensitive matching for flexibility
        found = any(required.lower() in s.lower() for s in normalized)
        if not found:
            missing.append(required)

    # Check any_of scopes (if any)
    if requirements["any_of"]:
        has_any = any(
            any(opt.lower() in s.lower() for s in normalized)
            for opt in requirements["any_of"]
        )
        if not has_any:
            missing.append(f"one of: {', '.join(requirements['any_of'])}")

    return {
        "meets_requirements": len(missing) == 0,
        "missing_scopes": missing,
        "level": level.value,
        "level_name": level.display_name,
    }


def detect_level(scopes: list[str], provider: str) -> dict[str, Any]:
    """
    Detect the highest integration level supported by granted scopes.

    Args:
        scopes: List of granted OAuth scopes
        provider: 'google' or 'microsoft'

    Returns:
        dict with detected_level, level_name, can_upgrade, upgrade_scopes
    """
    if not scopes:
        return {
            "success": True,
            "detected_level": IntegrationLevel.SANDBOXED.value,
            "level_name": IntegrationLevel.SANDBOXED.display_name,
            "can_upgrade": True,
            "next_level": IntegrationLevel.READ_ONLY.value,
        }

    # Check from highest to lowest level
    levels_to_check = [
        IntegrationLevel.AUTONOMOUS,
        IntegrationLevel.MANAGED_PROXY,
        IntegrationLevel.COLLABORATIVE,
        IntegrationLevel.READ_ONLY,
    ]

    detected = IntegrationLevel.SANDBOXED
    for level in levels_to_check:
        result = check_level_requirements(scopes, provider, level)
        if result["meets_requirements"]:
            detected = level
            break

    # Find next level upgrade possibility
    can_upgrade = detected.value < IntegrationLevel.AUTONOMOUS.value
    next_level = None
    upgrade_scopes = []

    if can_upgrade:
        next_level_enum = IntegrationLevel(detected.value + 1)
        next_result = check_level_requirements(scopes, provider, next_level_enum)
        next_level = next_level_enum.value
        upgrade_scopes = next_result.get("missing_scopes", [])

    return {
        "success": True,
        "detected_level": detected.value,
        "level_name": detected.display_name,
        "level_description": detected.description,
        "can_upgrade": can_upgrade,
        "next_level": next_level,
        "next_level_name": IntegrationLevel(next_level).display_name if next_level else None,
        "upgrade_requires": upgrade_scopes,
        "provider": provider,
        "scopes_analyzed": len(scopes),
    }


def detect_level_for_account(account_id: str) -> dict[str, Any]:
    """
    Detect integration level for a specific account.

    Args:
        account_id: Office account ID

    Returns:
        dict with detected level and upgrade suggestions
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT provider, scopes, integration_level FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": "Account not found"}

    provider = row["provider"]
    scopes = json.loads(row["scopes"]) if row["scopes"] else []
    stored_level = row["integration_level"]

    result = detect_level(scopes, provider)

    # Compare with stored level
    if result["success"]:
        result["stored_level"] = stored_level
        result["level_mismatch"] = result["detected_level"] != stored_level

        if result["level_mismatch"]:
            result["recommendation"] = (
                f"Stored level ({stored_level}) differs from detected level "
                f"({result['detected_level']}). Consider updating the account."
            )

    return result


def suggest_level_for_use_case(use_case: str) -> dict[str, Any]:
    """
    Suggest appropriate integration level for a use case.

    Args:
        use_case: Description of what user wants to do

    Returns:
        dict with suggested level and rationale
    """
    use_case_lower = use_case.lower()

    # Keywords mapped to levels
    level_keywords = {
        IntegrationLevel.READ_ONLY: [
            "read", "view", "see", "check", "summary", "summarize",
            "what's in", "inbox", "calendar", "schedule",
        ],
        IntegrationLevel.COLLABORATIVE: [
            "draft", "write", "compose", "schedule meeting", "create event",
            "prepare", "help me write",
        ],
        IntegrationLevel.MANAGED_PROXY: [
            "send", "reply", "respond", "forward", "delete",
            "manage", "handle", "take care of",
        ],
        IntegrationLevel.AUTONOMOUS: [
            "automate", "auto-reply", "automatically", "manage for me",
            "handle everything", "full control", "run my inbox",
        ],
    }

    # Score each level
    scores = {}
    for level, keywords in level_keywords.items():
        score = sum(1 for kw in keywords if kw in use_case_lower)
        scores[level] = score

    # Find best match
    best_level = max(scores, key=scores.get)
    if scores[best_level] == 0:
        best_level = IntegrationLevel.READ_ONLY  # Safe default

    return {
        "success": True,
        "suggested_level": best_level.value,
        "level_name": best_level.display_name,
        "level_description": best_level.description,
        "risk_level": best_level.risk_level,
        "use_case": use_case,
        "rationale": _get_suggestion_rationale(best_level, use_case),
    }


def _get_suggestion_rationale(level: IntegrationLevel, use_case: str) -> str:
    """Generate explanation for level suggestion."""
    rationales = {
        IntegrationLevel.SANDBOXED: (
            "For maximum privacy, Dex uses its own email account. "
            "You forward messages you want Dex to see."
        ),
        IntegrationLevel.READ_ONLY: (
            "Dex can read your inbox and calendar to provide summaries and suggestions, "
            "but cannot take any actions on your behalf."
        ),
        IntegrationLevel.COLLABORATIVE: (
            "Dex can create drafts and schedule meetings for you to review. "
            "Nothing is sent without your approval."
        ),
        IntegrationLevel.MANAGED_PROXY: (
            "Dex can send emails and manage your calendar with a 60-second undo window. "
            "All actions are logged for accountability."
        ),
        IntegrationLevel.AUTONOMOUS: (
            "Dex manages your email and calendar based on policies you define. "
            "Recommended only after building trust with lower levels first."
        ),
    }
    return rationales.get(level, "")


def get_level_comparison() -> dict[str, Any]:
    """
    Get a comparison of all integration levels.

    Returns:
        dict with level details for display
    """
    levels = []
    for level in IntegrationLevel:
        levels.append({
            "level": level.value,
            "name": level.display_name,
            "description": level.description,
            "risk": level.risk_level,
            "capabilities": _get_level_capabilities(level),
        })

    return {"success": True, "levels": levels}


def _get_level_capabilities(level: IntegrationLevel) -> list[str]:
    """Get list of capabilities for a level."""
    capabilities = {
        IntegrationLevel.SANDBOXED: [
            "Dex has own email address",
            "You forward messages to share",
            "Dex sends from its own identity",
        ],
        IntegrationLevel.READ_ONLY: [
            "Read your inbox",
            "Read your calendar",
            "Summarize emails",
            "Answer 'What's on my schedule?'",
        ],
        IntegrationLevel.COLLABORATIVE: [
            "Everything in Read-Only",
            "Create email drafts",
            "Schedule meetings as you",
            "Update calendar events",
        ],
        IntegrationLevel.MANAGED_PROXY: [
            "Everything in Collaborative",
            "Send emails (with 60s undo)",
            "Delete emails (with confirmation)",
            "Full audit trail",
            "Daily action digest",
        ],
        IntegrationLevel.AUTONOMOUS: [
            "Everything in Managed Proxy",
            "Auto-reply to emails",
            "Auto-manage calendar",
            "Policy-based automation",
            "Background processing",
        ],
    }
    return capabilities.get(level, [])


def main():
    parser = argparse.ArgumentParser(description="Office Integration Level Detector")
    parser.add_argument("--account-id", help="Account ID to analyze")
    parser.add_argument("--scopes", help="Space-separated scopes to analyze")
    parser.add_argument("--provider", choices=["google", "microsoft"], help="Provider")
    parser.add_argument("--use-case", help="Use case to suggest level for")
    parser.add_argument("--compare", action="store_true", help="Show level comparison")

    args = parser.parse_args()

    if args.compare:
        result = get_level_comparison()
        for level in result["levels"]:
            print(f"\n=== Level {level['level']}: {level['name']} ===")
            print(f"Risk: {level['risk']}")
            print(f"Description: {level['description']}")
            print("Capabilities:")
            for cap in level["capabilities"]:
                print(f"  - {cap}")

    elif args.account_id:
        result = detect_level_for_account(args.account_id)
        print(json.dumps(result, indent=2))

    elif args.scopes and args.provider:
        scopes = args.scopes.split()
        result = detect_level(scopes, args.provider)
        print(json.dumps(result, indent=2))

    elif args.use_case:
        result = suggest_level_for_use_case(args.use_case)
        print(f"Suggested level: {result['level_name']} (Level {result['suggested_level']})")
        print(f"Risk: {result['risk_level']}")
        print(f"\n{result['rationale']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
